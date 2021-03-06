from flask import render_template, jsonify, session, request, redirect, url_for
from retrobiocat_web.app.biocatdb import bp
import mongoengine as db
from retrobiocat_web.app.biocatdb.functions import sequence_table
from retrobiocat_web.mongo.models.biocatdb_models import EnzymeType, Paper
from retrobiocat_web.app.biocatdb.forms import SequenceSearch



@bp.route("/sequence_search", methods=["GET", "POST"])
def sequence_search():
    form = SequenceSearch()
    form.set_choices()

    if form.validate_on_submit() == True:
        form_data = form.data
        enzyme_type = form_data['enzyme_type']
        only_reviewed = form_data['only_reviewed']

        if only_reviewed is not True:
            if enzyme_type == 'All':
                return redirect(url_for("biocatdb.show_sequences"))
            else:
                return redirect(url_for("biocatdb.show_sequences", enzyme_type=form_data['enzyme_type']))
        else:
            if enzyme_type == 'All':
                return redirect(url_for("biocatdb.show_sequences", reviewed='reviewed'))
            else:
                return redirect(url_for("biocatdb.show_sequences", reviewed='reviewed', enzyme_type=form_data['enzyme_type']))

    return render_template('sequence_query/sequence_query.html', form=form)


# "localhost:5000/sequences?enzyme_type=CAR&paper_id=24934239"
@bp.route("/sequences", methods=["GET"])
def show_sequences():

    args = request.args.to_dict()
    title = "Enzyme sequences"

    if 'reviewed' in args:
        revQ = db.Q(reviewed=True)
    else:
        revQ = db.Q()
        title += " (including not reviewed)"

    if 'enzyme_type' in args:
        enzyme_type_query = db.Q(enzyme_type=args['enzyme_type'])
        title += f" for {args['enzyme_type']} enzymes"
    else:
        enzyme_type_query = db.Q()

    if 'paper_id' in args:
        paper_query = db.Q(papers=args['paper_id'])
        paper = Paper.objects(id=args['paper_id'])[0]
        title += f" in {paper.short_citation}"
    else:
        paper_query = db.Q()

    enzyme_data = sequence_table.get_enzyme_data(enzyme_type_query & paper_query & revQ)
    enzyme_types = sorted(list(EnzymeType.objects().distinct("enzyme_type")))

    return render_template('edit_tables/edit_sequences.html',
                           seq_data=enzyme_data,
                           seq_button_columns=[],
                           seq_table_height='80vh',
                           enzyme_types=enzyme_types,
                           show_header_filters=True,
                           include_owner=True,
                           lock_enz_type='false',
                           title=title,
                           row_click_modal=True)

