from retrobiocat_web.app.db_analysis import bp
from flask import render_template, flash, redirect, url_for, request, jsonify, session, current_app
from flask_security import roles_required, current_user
from retrobiocat_web.mongo.models.biocatdb_models import Paper, Activity, Sequence, Molecule, Tag, EnzymeType, UniRef90, UniRef50, Alignment, SeqSimNet, SSN_record
from retrobiocat_web.analysis import embl_restfull, all_by_all_blast, make_ssn, ssn_tasks
from rq.registry import StartedJobRegistry
import datetime
import mongoengine as db
import shutil
import os
from pathlib import Path
from rq.job import Job
import time
from retrobiocat_web.analysis import embl_restfull



@bp.route('/_find_homologs', methods=['GET', 'POST'])
@roles_required('admin')
def find_homologs():
    enzyme_type = request.form['enzyme_type']
    embl_restfull.set_blast_jobs(enzyme_type)

    result = {'status': 'success',
              'msg': f"Started job to blast all {enzyme_type}'s",
              'issues': []}


    return jsonify(result=result)

@bp.route('/_find_all_homologs', methods=['GET', 'POST'])
@roles_required('admin')
def find_allhomologs():

    enzyme_types = EnzymeType.objects().distinct('enzyme_type')

    for enzyme_type in enzyme_types:
        embl_restfull.set_blast_jobs(enzyme_type)

    result = {'status': 'success',
              'msg': f"Started job to blast all enzyme_type's",
              'issues': []}

    return jsonify(result=result)

@bp.route('/_expand_ssn', methods=['GET', 'POST'])
@roles_required('admin')
def expand_ssn():
    enzyme_type = request.form['enzyme_type']
    job_name = f"{enzyme_type}_expand_ssn"
    current_app.alignment_queue.enqueue(ssn_tasks.task_expand_ssn, enzyme_type, job_id=job_name)

    result = {'status': 'success',
              'msg': f"Launched expand ssn for {enzyme_type}'s",
              'issues': []}

    return jsonify(result=result)

@bp.route('/bioinformatics_admin_page', methods=['GET', 'POST'])
@roles_required('admin')
def bioinformatics_admin_page():
    enzyme_types = EnzymeType.objects().order_by('enzyme_type')

    biostat = {}
    ssn = {}
    for enz_type_obj in enzyme_types:
        enz_type = enz_type_obj.enzyme_type
        biostat[enz_type] = enz_type_obj.bioinformatics_status
        q = SSN_record.objects(enzyme_type=enz_type_obj)
        if len(q) != 0:
            ssn[enz_type] = q[0].status
        else:
            ssn[enz_type] = 'None'

    enzyme_numbers = {}
    for enz_type_obj in enzyme_types:
        enz_type = enz_type_obj.enzyme_type
        enzyme_numbers[enz_type] = {}
        enzyme_numbers[enz_type]['biocatdb'] = len(Sequence.objects(enzyme_type=enz_type))
        enzyme_numbers[enz_type]['uniref'] = len(UniRef50.objects(enzyme_type=enz_type_obj))

    enz_type_dict = {}
    for enz_type_obj in enzyme_types:
        enz_type = enz_type_obj.enzyme_type
        enz_type_dict[enz_type] = 0
        seqs = Sequence.objects(enzyme_type=enz_type)
        if len(seqs) != 0:
            for seq in seqs:
                if seq.blast is not None:
                    enz_type_dict[enz_type] += 1
            if enz_type_dict[enz_type] != 0:
                enz_type_dict[enz_type] = round((enz_type_dict[enz_type]/len(seqs))*100, 0)

    registry = StartedJobRegistry(queue=current_app.blast_queue)
    num_jobs = registry.count

    return render_template('bioinformatics/bioinformatics_admin.html',
                           blasted_enz_types=enz_type_dict,
                           biostat=biostat,
                           ssn=ssn,
                           num_jobs=num_jobs,
                           enzyme_numbers=enzyme_numbers)

@bp.route('/_clear_all_bioinformatics_data', methods=['GET', 'POST'])
@roles_required('admin')
def clear_all_bioinformatics_data():
    enzyme_types = EnzymeType.objects()
    seqs = Sequence.objects()

    for enz in enzyme_types:
        enz.bioinformatics_status = 'Idle'
        enz.save()

    for seq in seqs:
        seq.blast = None
        seq.alignments_made = None
        seq.save()

    UniRef50.drop_collection()
    SSN_record.drop_collection()

    UniRef90.drop_collection()
    Alignment.drop_collection()
    SeqSimNet.drop_collection()

    analysis_data_ssn = str(Path(__file__).parents[3]) + f'/analysis/analysis_data/ssn'
    analysis_data_aba = str(Path(__file__).parents[3]) + f'/analysis/analysis_data/all_by_all_blast'
    shutil.rmtree(analysis_data_ssn)
    shutil.rmtree(analysis_data_aba)
    os.mkdir(analysis_data_ssn)
    os.mkdir(analysis_data_aba)

    print('ALL BIOINFORMATICS DATA DELETED')

    result = {'status': 'success',
              'msg': f"Done",
              'issues': []}

    return jsonify(result=result)

@bp.route('/_mark_not_aligned', methods=['GET', 'POST'])
@roles_required('admin')
def mark_not_aligned():
    enzyme_type = request.form['enzyme_type']
    sequences = Sequence.objects(enzyme_type=enzyme_type)

    for seq in sequences:
        seq.alignments_made = False
        seq.save()

    enz_type_obj = EnzymeType.objects(enzyme_type=enzyme_type)[0]
    ssn_record = SSN_record.objects(enzyme_type=enz_type_obj)[0]
    ssn_record.status = 'Queued for update'
    ssn_record.save()

    result = {'status': 'success',
              'msg': f"Done",
              'issues': []}

    return jsonify(result=result)


