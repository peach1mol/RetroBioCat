from retrobiocat_web.app.contributions import bp
from flask import flash, url_for, request, jsonify
from flask_security import roles_required, current_user
from retrobiocat_web.mongo.models.biocatdb_models import Sequence, Activity, Paper, EnzymeType
from retrobiocat_web.app.app import user_datastore
from retrobiocat_web.app.contributions.functions import papers_functions, papers_crossref
import mongoengine as db
from distutils.util import strtobool

def unassign_seqs_in_paper(user, paper):
    seqs = Sequence.objects(papers=paper).select_related()

    for seq in seqs:
        user_owns_another_paper = False
        for seq_paper in seq.papers:
            if seq_paper.owner == user:
                user_owns_another_paper = True
                break

        if user_owns_another_paper == False:
            seq.owner = None
            seq.save()


@bp.route('/_save_paper', methods=['GET', 'POST'])
@roles_required('contributor')
def save_paper():
    user = user_datastore.get_user(current_user.id)
    paper = Paper.objects(id=request.form['paper_id'])[0]

    if (paper.owner != user) and (not current_user.has_role('super_contributor')):
        result = {'status': 'danger',
                  'msg': 'No access to edit this paper',
                  'issues': [],
                  'redirect': url_for("contributions.launch_add_paper")}
        return jsonify(result=result)

    paper.short_citation = request.form['short_cit']
    paper.doi = request.form['doi']
    paper.html = 'https://doi.org/' + request.form['doi']
    if request.form['date'] != "":
        paper.date = request.form['date']
    paper.title = request.form['title']
    paper.journal = request.form['journal']
    paper.authors = request.form['authors'].split(', ')
    paper.tags = request.form['tags'].split(', ')
    if user not in paper.edits_by:
        paper.edits_by.append(user)

    if (paper.owner == user) and (request.form['self_assign'] == 'false'):
        paper.owner = None
        paper.save()
        unassign_seqs_in_paper(user, paper)
        if not current_user.has_role('super_contributor'):
            result = {'status': 'warning',
                      'msg': 'Paper no longer assigned to you',
                      'issues': [],
                      'redirect': url_for("contributions.launch_add_paper")}
            return jsonify(result=result)

    elif request.form['self_assign'] == 'true':
        paper.owner = user

    print(paper.to_json())
    paper.save()
    result = {'status': 'success',
              'msg': 'Paper information updated',
              'issues': []}
    return jsonify(result=result)


@bp.route('/_delete_paper', methods=['GET', 'POST'])
@roles_required('contributor')
def delete_paper():
    user = user_datastore.get_user(current_user.id)
    paper = Paper.objects(id=request.form['paper_id'])[0]

    if paper.owner != user and not user.has_role('super_contributor'):
        result = {'status': 'danger',
                  'msg': 'You are not the owner of this paper',
                  'issues': ['Assign this paper to yourself in order to delete it']}
        return jsonify(result=result)

    elif len(Sequence.objects(papers=paper)) != 0:
        result = {'status': 'danger',
                  'msg': 'Paper still contains sequences',
                  'issues': ['Please remove any sequences from paper before deleting']}
        return jsonify(result=result)

    elif len(Activity.objects(paper=paper)) != 0:
        result = {'status': 'danger',
                  'msg': 'Paper still contains activity data',
                  'issues': ['Please remove any activity data from paper before deleting']}
        return jsonify(result=result)

    else:
        paper.delete()

        result = {'status': 'success',
                  'msg': 'Paper deleted',
                  'issues': []}
        return jsonify(result=result)


@bp.route('/_query_pubmed', methods=['GET', 'POST'])
@roles_required('contributor')
def query_pubmed():
    paper = Paper.objects(id=request.form['paper_id'])[0]
    doi = str(paper.doi)

    title, authors_list, journal, date, cite_mini = papers_functions.query_pubmed(doi)
    print(f"{title}, {authors_list}, {journal}, {type(date)}, {date}, {cite_mini}")

    if cite_mini == '':
        result = {'status': 'danger',
                  'msg': 'DOI not found in pubmed',
                  'issues': []}

    else:
        paper_dict = {'short_cit': cite_mini,
                      'doi': doi,
                      'date': str(date),
                      'title': title,
                      'journal': journal,
                      'authors': papers_functions.list_to_string(authors_list)}

        result = {'status': 'success',
                  'msg': 'Fields updated, click save to update the database',
                  'issues': [],
                  'paper': paper_dict}

    return jsonify(result=result)

@bp.route('/_query_crossref', methods=['GET', 'POST'])
@roles_required('contributor')
def query_crossref():
    paper = Paper.objects(id=request.form['paper_id'])[0]
    doi = str(paper.doi)

    title, authors_list, journal, date, cite_mini = papers_crossref.get_metadata_from_crossref(doi)

    print(f"{title}, {authors_list}, {journal}, {type(date)}, {cite_mini}")

    if cite_mini == '':
        result = {'status': 'danger',
                  'msg': 'DOI not found in crossref',
                  'issues': []}

    else:
        paper_dict = {'short_cit': cite_mini,
                      'doi': doi,
                      'date': str(date),
                      'title': title,
                      'journal': journal,
                      'authors': papers_functions.list_to_string(authors_list)}

        result = {'status': 'success',
                  'msg': 'Fields updated, click save to update the database',
                  'issues': [],
                  'paper': paper_dict}

    return jsonify(result=result)


@bp.route('/_add_new_enzymes', methods=['GET', 'POST'])
@roles_required('contributor')
def add_new_enzymes():
    enzyme_type = request.form['enzyme_type']
    existing_name = request.form['existing_name']
    new_name = request.form['new_name']
    user = user_datastore.get_user(current_user.id)
    paper = Paper.objects(id=request.form['paper_id'])[0]

    if existing_name == new_name and new_name == "":
        result = {'status': 'danger',
                  'msg': 'Must select an enzyme or enter a new name',
                  'issues': []}

    elif existing_name != "" and new_name != "":
        result = {'status': 'danger',
                  'msg': 'Choose either an existing enzyme or enter a new name',
                  'issues': ["(One must be blank)"]}

    elif existing_name != "":
        seq = Sequence.objects(enzyme_name=existing_name)[0]
        seq.papers.append(paper)
        seq.save()
        result = {'status': 'success',
                  'msg': 'Sequence added to paper',
                  'issues': []}

    elif new_name != "":
        seq = Sequence(enzyme_name=new_name,
                       enzyme_type=enzyme_type,
                       added_by=user,
                       owner=user,
                       papers=[paper])
        seq.save()

        if user not in paper.edits_by:
            paper.edits_by.append(user)

        papers_functions.tag_paper_with_enzyme_types(paper)

        result = {'status': 'success',
                  'msg': 'Sequence added to paper',
                  'issues': []}
    else:
        result = {'status': 'danger',
                  'msg': 'Error creating new enzyme',
                  'issues': []}

    return jsonify(result=result)


@bp.route('/_remove_seq_from_paper', methods=['GET', 'POST'])
@roles_required('contributor')
def remove_sequence():
    user = user_datastore.get_user(current_user.id)
    paper = Paper.objects(id=request.form['paper_id'])[0]

    enzyme_name = request.form['enzyme_name']
    seq = Sequence.objects(enzyme_name=enzyme_name)[0]

    if len(Activity.objects(db.Q(enzyme_name=seq.enzyme_name) & db.Q(paper=paper))) != 0:
        result = {'status': 'danger',
                  'msg': 'Can not remove sequence - activity data still attached',
                  'issues': ['Please remove references to this sequence in the activity section before removing']}
        return jsonify(result=result)

    else:
        if paper in seq.papers:
            seq.papers.remove(paper)
            seq.save()
        if len(seq.papers) == 0 and (seq.sequence == '' or seq.sequence is None):
            seq.delete()

    papers_functions.tag_paper_with_enzyme_types(paper)

    result = {'status': 'success',
              'msg': 'Sequence removed from paper',
              'issues': []}
    flash("Sequence removed from paper", 'success')
    return jsonify(result=result)


@bp.route('/_review_paper', methods=['GET', 'POST'])
@roles_required('super_contributor')
def review_paper():
    paper = Paper.objects(id=request.form['paper_id'])[0]
    reviewed = bool(strtobool(request.form['reviewed']))
    paper.reviewed = reviewed
    paper.save()

    flash("Paper review status updated", 'success')
    return jsonify({})

@bp.route('/_self_assign', methods=['GET', 'POST'])
@roles_required('contributor')
def self_assign():
    paper = Paper.objects(id=request.form['paper_id'])[0]
    user = user_datastore.get_user(current_user.id)

    if papers_functions.can_self_assign(user) == False:
        result = {'status': 'danger',
                  'msg': 'Can not assign paper',
                  'issues': ['Users may not have more papers assigned to them than the number they have completed',
                             'Please complete papers already assigned to you before taking on additional papers']}
        return jsonify(result=result)

    if paper.owner == None:
        paper.owner = user
        paper.save()
        result = {'status': 'success',
                  'msg': 'Paper is now assigned to you',
                  'issues': []}
        flash("Paper is now assigned to you", 'success')
        return jsonify(result=result)

    else:
        result = {'status': 'danger',
                  'msg': 'Could not assign, paper already belongs to another user',
                  'issues': []}
        return jsonify(result=result)

