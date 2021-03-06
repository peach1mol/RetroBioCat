from retrobiocat_web.mongo.models.biocatdb_models import Sequence, EnzymeType, UniRef90
import mongoengine as db

def new_node(seq_obj):

    if 'UniRef50' in seq_obj.enzyme_name:
        colour = 'darkblue'
        node_type = 'uniref'
    else:
        colour = 'darkred'
        node_type = 'biocatdb'

    if hasattr(seq_obj, 'protein_name') and hasattr(seq_obj, 'tax') :
        title = f"{seq_obj.protein_name} - {seq_obj.tax}"
    else:
        title = seq_obj.enzyme_name

    node = {'id': seq_obj.enzyme_name,
            'size': 40,
            'borderWidth': 1,
            'borderWidthSelected': 3,
            'color': {'background': colour, 'border': 'black'},
            'label': seq_obj.enzyme_name,
            'title': title,
            'shape': 'dot',
            'node_type': node_type}

    return node

def new_edge(ali_obj):
    seq_1 = ali_obj.proteins[0]
    seq_2 = ali_obj.proteins[1]

    edge = {'id': f"from {seq_1.enzyme_name} to {seq_2.enzyme_name}",
            'from': seq_1.enzyme_name,
            'to': seq_2.enzyme_name}
    return edge

def get_nodes_and_edges(enzyme_type, identity):
    enz_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]
    alignments = []

    sequences = Sequence.objects(db.Q(sequence__ne=None) & db.Q(sequence__ne='') & db.Q(enzyme_type=enzyme_type))
    unirefs = UniRef90.objects(enzyme_type=enz_type_obj)

    nodes = []
    for seq_obj in list(unirefs) + list(sequences):
        nodes.append(new_node(seq_obj))

    edges = []
    for ali_obj in alignments:
        if ali_obj.identity >= identity and ali_obj.proteins[0].enzyme_name != ali_obj.proteins[1].enzyme_name:
            edges.append(new_edge(ali_obj))

    return nodes, edges


if __name__ == '__main__':
    from retrobiocat_web.mongo.default_connection import make_default_connection
    make_default_connection()

    enzyme_type = 'AAD'
    sequences = Sequence.objects(db.Q(sequence__ne=None) & db.Q(sequence__ne='') & db.Q(enzyme_type=enzyme_type))

    for seq in sequences:
        print(seq.enzyme_name)
        print(f"Sequence = '{seq.sequence}'")
