from Bio import SeqIO
# from Bio.Blast import NCBIWWW, NCBIXML
# from Bio.Blast.Applications import *
import os
import pandas as pd
from models import *
from plot import *


# HELPER FUNCTIONS -----------------------------------------------------------------------------------------------------

# Helper: Parse through GenBank's gene location string (used by parse_genbank). used. 
def parse_location(location_stg):
    start = ""
    stop = ""
    frame = ""
    parsed = []
    location_stg = str(location_stg)
    for char in location_stg:
        if char is "[" or char is "]":
            parsed.append(char)
        elif char is ":":
            parsed.append(char)
        elif char is "(" or char is ")":
            parsed.append(char)
        elif char.isdigit() and ":" not in parsed:
            start = start + char
        elif char.isdigit() and ":" in parsed:
            stop = stop + char
        elif "(" in parsed:
            frame = char
    start = int(start) + 1
    stop = int(stop)
    return [start, stop, frame]


# Helper: to parse through GeneMark ldata (used by parse_genemark_ldata). used.
def get_keys_by_value(dict, value_to_find):
	keys = list()
	items = dict.items()
	for item in items:
		if value_to_find in item[1]:
			keys.append(item[0])
	return keys


# Helper: add probabilities for each frame (used by make_avg_prob_dict)
def add_frame_probs(df, base_positions):
	one = []
	two = []
	three = []
	four = []
	five = []
	six = []
	for base in base_positions:
		one.append(df.loc[base, '1'])
		two.append(df.loc[base, '2'])
		three.append(df.loc[base, '3'])
		four.append(df.loc[base, '4'])
		five.append(df.loc[base, '5'])
		six.append(df.loc[base, '6'])
	return [one, two, three, four, five, six]


# Helper: Find average (used by make_avg_prob_dict)
def calculate_avg_prob(probabilities):
	total = 0
	for probability in probabilities:
		total += probability

	average = total / len(probabilities)
	return round(average, 8)


# Helper: Make dictionary {key: frame #, value: avg probability} (used by failed_genes)
def make_avg_prob_dict(df, start, stop):
	indexes = []
	for index, row in df.iterrows():
		if start <= index <= stop:
			indexes.append(index)

	frames = add_frame_probs(df, indexes)
	avg_probs = {}
	current_frame = 1
	for frame in frames:
		avg_prob = calculate_avg_prob(frame)
		frame_label = "frame_{}".format(current_frame)
		avg_probs[frame_label] = avg_prob
		current_frame = current_frame + 1

	return avg_probs


# Helper: Parse through BLAST file (used by translate_and_blast)
# FIXME: Parse BLAST output. Not finished.
def parse_blast(file):
	# E_VALUE_THRESH = 0.04
	result_handle = open(file)
	blast_record = NCBIXML.read(result_handle)
	for alignment in blast_record.alignments:
		for hsp in alignment.hsps:
			# if hsp.expect < E_VALUE_THRESH:
			print("****Alignment****")
			print("sequence:", alignment.title)
			print("length:", alignment.length)
			print("e value:", hsp.expect)
			print(hsp.query[0:75] + "...")
			print(hsp.match[0:75] + "...")
			print(hsp.sbjct[0:75] + "...")


# MAIN FUNCTIONS ------------------------------------------------------------------------------------------------------

# Get all gene locations from GenBank file and add to sql database
def parse_genbank(genbank_file):
    with open(genbank_file, "r") as handle:
        for record in SeqIO.parse(handle, "genbank"):
            id_number = 1
            for feature in record.features:
                if feature.type == "CDS":
                    id = "dnamaster_" + str(id_number)
                    gene_info = parse_location(feature.location)
                    cds = DNAMaster(id=id,
                                    start=gene_info[0],
                                    stop=gene_info[1],
                                    strand=gene_info[2],
									function="None",
                                    status="None")
                    exists = DNAMaster.query.filter_by(id=id).first()
                    if not exists:
                        db.session.add(cds)
                        db.session.commit()
                        id_number += 1


# Parse through genemark ldata
def parse_genemark_ldata(gm_file):
    genemark_all_genes = dict()
    with open(gm_file, "r") as handle:
        for line in handle:
            if line == '\n':
                break
            if line[0] != '#':
                column = line.strip().split()
                start = int(column[0])
                stop = int(column[1])
                if stop not in genemark_all_genes:
                    genemark_all_genes[stop] = [start]
                else:
                    if start not in genemark_all_genes[stop]:
                        genemark_all_genes[stop].append(start)
                curr_keys = get_keys_by_value(genemark_all_genes, start)
                if len(curr_keys) > 1:
                    max_right = max(curr_keys)
                    for key in curr_keys:
                        if key != max_right:
                            del genemark_all_genes[key]

    genemark_genes = dict()
    with open(gm_file, "r") as handle:
        for line in handle:
            if line == '\n':
                break
            if line[0] != '#':
                column = line.strip().split()
                curr_start = int(column[0])
                curr_stop = int(column[1])
                frame = int(column[2])
                if 1 <= frame <= 3:
                    curr_frame = "+"
                elif 4 <= frame <= 6:
                    curr_frame = "-"
                id_number = 1
                for stop in genemark_all_genes:
                    min_start = min(genemark_all_genes[stop])
                    if min_start == curr_start and stop == curr_stop:
                        if (min_start, stop) not in genemark_genes:
                            id = "genemark_" + str(id_number)
                            genemark_genes[(min_start, stop)] = curr_frame
                            cds = GeneMark(id=id,
                                           start=min_start,
                                           stop=stop,
                                           strand=curr_frame)
                            exists = GeneMark.query.filter_by(id=id).first()
                            if not exists:
                                db.session.add(cds)
                                db.session.commit()
                    id_number += 1


# Compare the gene calls between each tool
def compare():
	for cds in DNAMaster.query.all():
		dnamaster_cds = DNAMaster.query.filter_by(stop=cds.stop).first()
		genemark_cds = GeneMark.query.filter_by(stop=cds.stop).first()
		if dnamaster_cds and genemark_cds:
			if dnamaster_cds.start <= genemark_cds.start:
				dnamaster_cds.status = "Pass"
			else:
				dnamaster_cds.status = "Fail"
		elif not genemark_cds:
			dnamaster_cds.status = "Not called by GeneMark"
		db.session.commit()


# Deals with "failed" genes.
def failed_gene(cds_id, fasta_file, genemark_gdata_file):
	gdata_df = pd.read_csv(genemark_gdata_file, sep='\t', skiprows=16)
	gdata_df.columns = ['Base', '1', '2', '3', '4', '5', '6']
	gdata_df = gdata_df.set_index('Base')

	bacteria_start_codons = ["ATG", "GTG", "TTG"]
	record = SeqIO.read(fasta_file, "fasta")
	failed_gene = DNAMaster.query.filter_by(id=cds_id, status="Fail").first()
	genemark_gene = GeneMark.query.filter_by(stop=failed_gene.stop).first()

	actual_start = failed_gene.start - 1  # Subtract 1 because indexing begins with 0.
	next_start_position = actual_start - 3  # Subtract 3 to account for 3 bases in a codon.
	start_positions = {}
	while next_start_position >= genemark_gene.start-3:
		if failed_gene.strand == '+':
			previous_codon = record.seq[next_start_position:next_start_position + 3]
		elif failed_gene.strand == '-':
			previous_codon = record.seq.reverse_complement()[next_start_position:next_start_position + 3]
		if previous_codon in bacteria_start_codons:
			avg_dict = make_avg_prob_dict(gdata_df, next_start_position, failed_gene.stop)
			start_positions[next_start_position+1] = avg_dict
		next_start_position = next_start_position - 3

	# plot.make_plot_direct(genemark_gdata_file, failed_gene.start, failed_gene.stop, list(start_positions.keys()))
    # plot.make_plot_complementary(genemark_gdata_file, failed_gene.start, failed_gene.stop, list(start_positions.keys()))
	return start_positions


# Deals with 'Not called by GeneMark' genes.
def need_more_info_genes(cds_id, genemark_gdata_file):
	gdata_df = pd.read_csv(genemark_gdata_file, sep='\t', skiprows=16)
	gdata_df.columns = ['Base', '1', '2', '3', '4', '5', '6']
	gdata_df = gdata_df.set_index('Base')
	cds = DNAMaster.query.filter_by(id=cds_id, status="Not called by GeneMark").first()
	probabilities = make_avg_prob_dict(gdata_df, cds.start, cds.stop)
	return(probabilities)


# # FIXME: Translate to protein sequence and BLAST
# def translate_and_blast(cds):
# 	record = SeqIO.read("fern.fasta", "fasta")
# 	table = 11  # Bacterial code
# 	genome = record.seq

# 	curr_sequence = genome[cds.start: cds.stop].translate(table)
# 	result_handle = NCBIWWW.qblast("blastp", "nt", curr_sequence)
# 	with open("my_blast.xml", "w") as out_handle:
# 		out_handle.write(result_handle.read())
# 	result_handle.close()
# 	parse_blast("my_blast.xml")




# -----------------------
# def compare_all(db):
	# genemark_gdata_file = get_file("GeneMark_gdata")
	# gdata_df = pd.read_csv(genemark_gdata_file, sep='\t', skiprows=16)
	# gdata_df.columns = ['Base', '1', '2', '3', '4', '5', '6']
	# gdata_df = gdata_df.set_index('Base')

	# parse_genemark_gdata(gdata_df, db)
	# failed_genes("fern.fasta", db, gdata_df)
	# # translate_and_blast(db)
	# # final(db)

	# create_dnamaster_html(db)
	# # create_final_html(db)

