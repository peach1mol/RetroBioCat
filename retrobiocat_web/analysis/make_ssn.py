from retrobiocat_web.mongo.models.biocatdb_models import Sequence, EnzymeType, UniRef50, SeqSimNet
from retrobiocat_web.analysis.all_by_all_blast import AllByAllBlaster
from flask import render_template, flash, redirect, url_for, request, jsonify, session, current_app
import mongoengine as db
import networkx as nx
import time
import json
from rq.registry import StartedJobRegistry
from pathlib import Path
import os
import pandas as pd
from bson.binary import Binary


class SSN(object):

    def __init__(self, enzyme_type, include_mutants=True, aba_blaster=None, print_log=False):
        self.graph = nx.Graph()

        self.enzyme_type = enzyme_type
        self.enzyme_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]

        if aba_blaster is None:
            self.aba_blaster = AllByAllBlaster(enzyme_type, print_log=print_log)
        else:
            self.aba_blaster = aba_blaster

        self.node_metadata = {}

        self.print_log = print_log
        self.include_mutants = include_mutants

        self.save_path = str(Path(__file__).parents[0]) + f'/analysis_data/ssn/{self.enzyme_type}'
        if not os.path.exists(self.save_path):
            os.mkdir(self.save_path)

        self.log(f"SSN object initialised for {enzyme_type}")

        self.db_ssn = self._get_db_object()

    def save(self):
        t0 = time.time()

        graph_data = nx.to_dict_of_dicts(self.graph)

        att_dict = {}
        for node in list(self.graph):
            att_dict[node] = self.graph.nodes[node]

        self.db_ssn.graph_data.update(graph_data)
        self.db_ssn.node_attributes.update(att_dict)
        self.db_ssn.save()

        t1 = time.time()
        self.log(f"Saved SSN to Mongo, for {self.enzyme_type}, in {round(t1 - t0, 1)} seconds")

    def load(self):

        t0 = time.time()
        if self.db_ssn.graph_data is None:
            self.log(f"No data saved for {self.enzyme_type} SSN, could not load")
            return False

        self.graph = nx.from_dict_of_dicts(self.db_ssn.graph_data)

        # Nodes with no edges are not in edge list..
        for node in self.db_ssn.node_attributes:
            if node not in self.graph.nodes:
                self._add_protein_node(node)

        nx.set_node_attributes(self.graph, self.db_ssn.node_attributes)

        t1 = time.time()
        self.log(f"Loaded SSN for {self.enzyme_type} in {round(t1 - t0, 1)} seconds")

    def add_protein(self, seq_obj):
        """ Add the protein to the graph, along with any proteins which have alignments """

        self.log(f"Adding node - {seq_obj.enzyme_name} and making alignments..")
        t0 = time.time()

        name = seq_obj.enzyme_name
        self._add_protein_node(name, alignments_made=True)
        alignment_names, alignment_scores = self.aba_blaster.get_alignments(seq_obj)
        #self.graph.nodes[name]['attributes']['alignments_made'] = True

        count = 0
        for i, protein_name in enumerate(alignment_names):
            count += self._add_protein_node(protein_name)
            self._add_alignment_edge(seq_obj.enzyme_name, protein_name, alignment_scores[i])

        t1 = time.time()
        self.log(f"{count} new nodes made for alignments, with {len(alignment_names)} edges added")
        self.log(f"Protein {seq_obj.enzyme_name} processed in {round(t1-t0,0)} seconds")

    def add_multiple_proteins(self, list_seq_obj):
        for seq_obj in list_seq_obj:
            self.add_protein(seq_obj)

    def nodes_need_alignments(self, max_num=None):
        """ Return nodes which needs alignments making, maximum of max_num"""

        t0 = time.time()
        need_alignments = []
        count = 0
        for node in list(self.graph.nodes):
            if self.graph.nodes[node]['alignments_made'] == False:
                seq_obj = self._get_sequence_object(node)
                need_alignments.append(seq_obj)
                count += 1
                if count == max_num:
                    break

        t1 = time.time()
        self.log(f"Identified {count} nodes which need alignments making in {round(t1-t0,1)} seconds")

        return need_alignments

    def nodes_not_present(self, only_biocatdb=False, max_num=None):
        """ Return a list of enzymes which are not in the ssn """

        # Get a list of all sequence objects of enzyme type
        t0 = time.time()
        sequences = Sequence.objects(enzyme_type=self.enzyme_type)
        if only_biocatdb is True:
            seq_objects = list(sequences)
        else:
            unirefs = UniRef50.objects(enzyme_type=self.enzyme_type_obj)
            seq_objects = list(sequences) + list(unirefs)

        # Get sequences not in nodes
        not_in_nodes = []
        for seq_obj in seq_objects:
            if seq_obj.enzyme_name not in list(self.graph.nodes):
                not_in_nodes.append(seq_obj)

        # Return only up to the maximum number of sequences
        if max_num != None:
            if len(not_in_nodes) > max_num:
                not_in_nodes = not_in_nodes[0:max_num]

        t1 = time.time()
        self.log(f"Identified {len(not_in_nodes)} {self.enzyme_type} proteins which need adding, in {round(t1 - t0, 1)} seconds")
        return not_in_nodes

    def remove_nonexisting_seqs(self):

        t0 = time.time()
        sequences = Sequence.objects(enzyme_type=self.enzyme_type).distinct('enzyme_name')
        unirefs = UniRef50.objects(enzyme_type=self.enzyme_type_obj).distinct('enzyme_name')
        protein_names = list(sequences) + list(unirefs)
        count = 0
        for node in list(self.graph.nodes):
            if node not in protein_names:
                self.log(f"Node: {node} not in the database - removing")
                self.graph.remove_node(node)
                count += 1

        t1 = time.time()
        self.log(f"Identified {count} sequences which were in SSN but not in database, in {round(t1-t0,1)} seconds")

    def visualise(self, min_score=0):
        self._get_uniref_metadata()
        #pos_dict = nx.kamada_kawai_layout(self.graph, scale=4000)

        graph_nodes = list(self.graph.nodes)
        if self.include_mutants is True:
            graph_nodes = self._filter_out_mutants(graph_nodes)

        nodes = []
        edges = []
        for name in graph_nodes:
            nodes.append(self._visualise_new_node(name))

        for edge in self.graph.edges:
            edges.append(self._visualise_new_edge(edge))

        nodes = self._sort_biocatdb_nodes_to_front(nodes)

        return nodes, edges

    def get_graph_filtered_edges(self, min_weight=50):
        t0 = time.time()
        graph = self.graph.copy()
        for edge in graph:
            weight = graph.get_edge_data(edge[0], edge[1], default={'weight': 0})['weight']
            if weight < min_weight:
                graph.remove_edge(edge[0], edge[1])
        t1 = time.time()
        self.log(f"Created new graph with edges less than {min_weight} removed, in {round(t1-t0,1)} seconds")
        return graph

    def _filter_out_mutants(self, nodes):
        t0 = time.time()
        nodes = list(nodes)
        mutants = Sequence.objects(db.Q(enzyme_type=self.enzyme_type) & db.Q(mutant_of=''))
        for mutant in mutants:
            if mutant.enzyme_name in nodes:
                nodes.remove(mutant)
        t1 = time.time()
        self.log(f'Filtered mutants from graph in {round(t1-t0,1)} seconds')
        return nodes

    def _get_uniref_metadata(self):
        self.node_metadata = {}

        unirefs = UniRef50.objects(enzyme_type=self.enzyme_type_obj).exclude('id', 'enzyme_type', 'sequence', "result_of_blasts_for")

        for seq_obj in unirefs:
            if seq_obj.enzyme_name in self.graph.nodes:
                self.node_metadata[seq_obj.enzyme_name] = json.loads(seq_obj.to_json())

    def _add_protein_node(self, node_name, alignments_made=False):
        """ If a protein is not already in the graph, then add it """
        if 'UniRef50' in node_name:
            node_type = 'uniref'
        else:
            node_type = 'biocatdb'

        if node_name not in self.graph.nodes:
            self.graph.add_node(node_name, node_type=node_type,
                                alignments_made=alignments_made)
            return 1

        if alignments_made == True:
            self.graph.nodes[node_name]['alignments_made'] = True

        return 0

    def _add_alignment_edge(self, node_name, alignment_node_name, alignment_score):
        if node_name != alignment_node_name:
            self.graph.add_edge(node_name, alignment_node_name, weight=alignment_score)


    def log(self, msg):
        if self.print_log == True:
            print("SSN: " + msg)

    def _visualise_new_node(self, node_name, pos_dict=None):
        if 'UniRef50' in node_name:
            colour = 'darkblue'
            node_type = 'uniref'
        else:
            colour = 'darkred'
            node_type = 'biocatdb'

        metadata = self.node_metadata.get(node_name, {})
        protein_name = metadata.get('protein_name', '')
        tax = metadata.get('tax', '')
        if protein_name != '':
            label = f"{protein_name} - {tax}"
        else:
            label = node_name

        node = {'id': node_name,
                'size': 40,
                'borderWidth': 1,
                'borderWidthSelected': 3,
                'color': {'background': colour, 'border': 'black'},
                'label': label,
                'title': label,
                'shape': 'dot',
                'node_type': node_type,
                'metadata': metadata}

        if pos_dict is not None:
            x, y = tuple(pos_dict.get(node_name, (0, 0)))
            node['x'] = x
            node['y'] = y

        return node

    def _visualise_new_edge(self, edge):
        weight = self.graph.get_edge_data(edge[0], edge[1], default={'weight': 0})['weight']
        edge = {'id': f"from {edge[0]} to {edge[1]}",
                'from': edge[0],
                'to': edge[1],
                'weight': weight,
                'color': {'color': 'grey', 'opacity': 0.5}}
        return edge

    def _get_db_object(self):
        """ Either finds existing db entry for ssn of enzyme type, or makes a new one """

        query = SeqSimNet.objects(enzyme_type=self.enzyme_type_obj)
        if len(query) == 0:
            db_ssn = SeqSimNet(enzyme_type=self.enzyme_type_obj)
        else:
            db_ssn = query[0]

        return db_ssn

    def _sort_biocatdb_nodes_to_front(self, vis_nodes):
        """ Returns vis_nodes with any nodes marked as node_type='biocatdb' at the front """

        biocatdb_nodes = []
        other_nodes = []

        for node in vis_nodes:
            if 'biocatdb' in node.get('node_type', ''):
                biocatdb_nodes.append(node)
            else:
                other_nodes.append(node)

        return other_nodes + biocatdb_nodes

    @staticmethod
    def _get_sequence_object(enzyme_name):
        if 'UniRef50' in enzyme_name:
            return UniRef50.objects(enzyme_name=enzyme_name)[0]
        else:
            return Sequence.objects(enzyme_name=enzyme_name)[0]

def task_expand_ssn(enzyme_type, print_log=True, max_num=200):
    current_app.app_context().push()

    aba_blaster = AllByAllBlaster(enzyme_type, print_log=print_log)
    aba_blaster.make_blast_db()

    ssn = SSN(enzyme_type, aba_blaster=aba_blaster, print_log=print_log)
    ssn.load()
    ssn.remove_nonexisting_seqs()

    biocatdb_seqs = ssn.nodes_not_present(only_biocatdb=True, max_num=max_num)
    if len(biocatdb_seqs) != 0:
        ssn.add_multiple_proteins(biocatdb_seqs)
        ssn.save()
        current_app.alignment_queue.enqueue(new_expand_ssn_job, enzyme_type)
        return

    need_alignments = ssn.nodes_need_alignments(max_num=max_num)
    if len(need_alignments) != 0:
        ssn.add_multiple_proteins(need_alignments)
        ssn.save()
        current_app.alignment_queue.enqueue(new_expand_ssn_job, enzyme_type)
        return

    not_present = ssn.nodes_not_present(max_num=max_num)
    if len(not_present) != 0:
        ssn.add_multiple_proteins(not_present)
        ssn.save()
        current_app.alignment_queue.enqueue(new_expand_ssn_job, enzyme_type)

        return

    enz_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]
    enz_type_obj.bioinformatics_status = 'Idle'
    enz_type_obj.save()

def new_expand_ssn_job(enzyme_type):

    active_process_jobs = list(StartedJobRegistry(queue=current_app.alignment_queue).get_job_ids())
    active_process_jobs.extend(current_app.alignment_queue.job_ids)

    job_name = f"{enzyme_type}_expand_ssn"
    if job_name not in active_process_jobs:
        current_app.alignment_queue.enqueue(task_expand_ssn, enzyme_type, job_id=job_name)


if __name__ == '__main__':
    from retrobiocat_web.mongo.default_connection import make_default_connection
    make_default_connection()

    SeqSimNet.drop_collection()

    aad_ssn = SSN('AAD', print_log=True)
    aad_ssn.load()

    biocatdb_seqs = aad_ssn.nodes_not_present(only_biocatdb=True, max_num=10)
    aad_ssn.add_multiple_proteins(biocatdb_seqs)

    need_alignments = aad_ssn.nodes_need_alignments(max_num=10)
    aad_ssn.add_multiple_proteins(need_alignments)

    aad_ssn.filter_edges()

    nodes, edges = aad_ssn.visualise()
    print(nodes)



# 1. Start at high alignment score - 500
# 2. Find clusters



