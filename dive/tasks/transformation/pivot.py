import os
import pandas as pd
from flask import current_app

from dive.db import db_access
from dive.data.access import get_data
from dive.task_core import celery, task_app
from dive.tasks.pipelines import ingestion_pipeline
from dive.tasks.ingestion.upload import save_dataset
from dive.tasks.transformation.utilities import list_elements_from_indices, difference_of_lists, get_transformed_file_name


from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)


def unpivot_dataset(project_id, dataset_id, pivot_fields, variable_name, value_name, new_dataset_name_prefix):
    df = get_data(project_id=project_id, dataset_id=dataset_id)

    with task_app.app_context():
        project = db_access.get_project(project_id)
        original_dataset = db_access.get_dataset(project_id, dataset_id)

    preloaded_project = project.get('preloaded', False)
    if preloaded_project:
        project_dir = os.path.join(current_app.config['PRELOADED_DIR'], project['directory'])
    else:
        project_dir = os.path.join(current_app.config['UPLOAD_DIR'], str(project_id))

    original_dataset_title = original_dataset['title']
    fallback_title = original_dataset_title[:20]
    dataset_type = '.tsv'
    new_dataset_title, new_dataset_name, new_dataset_path = \
        get_transformed_file_name(project_dir, new_dataset_name_prefix, fallback_title, original_dataset_title, dataset_type)

    columns = df.columns.values
    pivot_fields = list_elements_from_indices(columns, pivot_fields)
    preserved_fields = difference_of_lists(columns, pivot_fields)
    df_unpivoted = pd.melt(df, id_vars=preserved_fields, value_vars=pivot_fields, var_name=variable_name, value_name=value_name)
    df_unpivoted.to_csv(new_dataset_path, sep='\t', index=False)

    dataset_docs = save_dataset(project_id, new_dataset_title, new_dataset_name, 'tsv', new_dataset_path)
    dataset_doc = dataset_docs[0]
    new_dataset_id = dataset_doc['id']

    ingestion_result = ingestion_pipeline(new_dataset_id, project_id).apply()

    return new_dataset_id
