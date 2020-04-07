from Bio import SeqIO, Seq, SeqFeature
from models import *
import os
import pandas as pd
import re
# from Bio.Blast import NCBIWWW, NCBIXML
# from Bio.Blast.Applications import *
# from plot import *


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
	return round(average, 4)


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

# Helper: Merge two lists into one list of lists (tuple in list form)
def merge(list1, list2): 
   merged_list = [] 
   for i in range(max((len(list1), len(list2)))): 
      while True: 
         try: 
            tup = [list1[i], list2[i]]
         except IndexError: 
            if len(list1) > len(list2): 
               list2.append('') 
               tup = [list1[i], list2[i]]
            elif len(list1) < len(list2): 
               list1.append('') 
               tup = [list1[i], list2[i]]
            continue
         merged_list.append(tup) 
         break
   return merged_list 


# Helper: Parse through BLAST file (used by translate_and_blast)
# FIXME: Parse BLAST output. Not finished.
# def parse_blast(file):
# 	# E_VALUE_THRESH = 0.04
# 	result_handle = open(file)
# 	blast_record = NCBIXML.read(result_handle)
# 	for alignment in blast_record.alignments:
# 		for hsp in alignment.hsps:
# 			# if hsp.expect < E_VALUE_THRESH:
# 			print("****Alignment****")
# 			print("sequence:", alignment.title)
# 			print("length:", alignment.length)
# 			print("e value:", hsp.expect)
# 			print(hsp.query[0:75] + "...")
# 			print(hsp.match[0:75] + "...")
# 			print(hsp.sbjct[0:75] + "...")


# MAIN FUNCTIONS ------------------------------------------------------------------------------------------------------

# Get all gene locations from GenBank file and add to sql database
def parse_genbank(genbank_file):
    with open(genbank_file, "r") as handle:
        for record in SeqIO.parse(handle, "genbank"):
            # id_number = 1
            for feature in record.features:
                if feature.type == "CDS":
                	# id = "dnamaster_" + str(id_number)
                    id = feature.qualifiers["locus_tag"][0]
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
                        # id_number += 1


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
			dnamaster_cds.status = "Need more information"
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
	cds = DNAMaster.query.filter_by(id=cds_id, status="Need more information").first()
	probabilities = make_avg_prob_dict(gdata_df, cds.start, cds.stop)
	return(probabilities)


# --------------------------
# Get start options for failed gene
def get_starts(cds_id, genome):
   bacteria_start_codons = ["ATG", "GTG", "TTG"]
   dnamaster = DNAMaster.query.filter_by(id=cds_id, status="Fail").first()
   genemark = GeneMark.query.filter_by(stop=dnamaster.stop).first()

   start = (dnamaster.start - 1) - 3  #  Subtract 1 because indexing begins with 0. Subtract 3 to account for 3 bases in a codon.
   starts = []
   while start >= genemark.start - 9:
      if dnamaster.strand == '+':
         codon = genome[start: start + 3]
      elif dnamaster.strand == '-':
         codon = genome.reverse_complement()[start: start + 3]
      if codon in bacteria_start_codons:
         starts.append(start + 1)
      start = start - 3

   return starts

# Get forward or reverse sequence
def get_sequence(genome, strand, start, stop):
   if strand == '-':
      return genome.reverse_complement()[start - 1: stop]
   else:
      return genome[start - 1: stop]

# Create FASTA for input into BLAST
def create_fasta(fasta_file, genemark_gdata_file):
   record = SeqIO.read(fasta_file, "fasta")
   genome = record.seq
   output = ""

   for cds in db.session.query(DNAMaster).order_by(DNAMaster.start):
      if cds.status == "Pass" or cds.status == "Need more information":
         output += f">{cds.id}, {cds.start}-{cds.stop}\n"
         output += f"{Seq.translate(sequence=get_sequence(genome, cds.strand, cds.start, cds.stop), table=11)}\n"
      elif cds.status == "Fail":
         output += f">{cds.id}, {cds.start}-{cds.stop}\n"
         output += f"{Seq.translate(sequence=get_sequence(genome, cds.strand, cds.start, cds.stop), table=11)}\n"
         starts = get_starts(cds.id, genome)
         for i in range(len(starts)):
            output += f">{cds.id}_{i + 1}, {starts[i]}-{cds.stop}\n"
            output += f"{Seq.translate(sequence=get_sequence(genome, cds.strand, starts[i], cds.stop), table=11)}\n"

   with open("sequences.fasta", "w") as out_handle:
      out_handle.write(output)
   
   return "sequences.fasta"

# Create modified GenBank file for input into Sequin
def modify_gb(gb_file):
   out_file_init = re.search(r'uploads/(.*).(\w*)', gb_file)
   out_file = str(out_file_init.group(1)) + '_modified.' + str(out_file_init.group(2))
   final_genes = create_final_dict()
   final_features = []
   for record in SeqIO.parse(open(gb_file, "r"), "genbank"):
      for feature in record.features:
         if feature.type == "gene" or feature.type == "CDS":
               locus_tag = feature.qualifiers["locus_tag"][0]
               if locus_tag in final_genes:
                  new_start = final_genes[locus_tag]['start']
                  if feature.location.strand == 1:
                     feature.location = SeqFeature.FeatureLocation(SeqFeature.ExactPosition(new_start - 1), 
                     SeqFeature.ExactPosition(feature.location.end.position), 
                     feature.location.strand)
                  else:
                     feature.location = SeqFeature.FeatureLocation(
                     SeqFeature.ExactPosition(feature.location.start.position),
                     SeqFeature.ExactPosition(new_start), feature.location.strand)
         final_features.append(feature)  # Append final features
      record.features = final_features
      with open(out_file, "w") as new_gb:
         SeqIO.write(record, new_gb, "genbank")
   return out_file


def create_final_dict():
	final_genes = {}
	row = {}
	for cds in DNAMaster.query.order_by(DNAMaster.start).all():
		row['start'] = cds.start
		row['strand'] = cds.strand
		final_genes[cds.id] = row
	return final_genes
	





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