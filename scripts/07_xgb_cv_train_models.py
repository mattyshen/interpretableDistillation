from imodelsx import submit_utils
from os.path import dirname, join
import os.path
repo_dir = dirname(dirname(os.path.abspath(__file__)))

# Showcasing different ways to sweep over arguments
# Can pass any empty dict for any of these to avoid sweeping

# List of values to sweep over (sweeps over all combinations of these)
params_shared_dict = {
    'seed': [0],
    'save_dir': [join(repo_dir, 'results/07_cv_train_model/xgb30')],
    'use_cache': [1], # pass binary values with 0/1 instead of the ambiguous strings True/False
}

# List of tuples to sweep over (these values are coupled, and swept over together)
# Note: this is a dictionary so you shouldn't have repeated keys

#datasets not completed = ["insurance", "qsar", "allstate", "mercedes", "transaction"]

params_coupled_dict = {}

#XGB params
params_coupled_dict.update({('dataset_name', 
                             'model_name', 
                             'max_depth'):
                            [(dn, mn, md) 
                             for dn in ["ca_housing", "abalone", "parkinsons", "airfoil", "cpu_act", "concrete", "powerplant", "miami_housing"]
                             for mn in ['xgboost30']
                             for md in [4, 5]
                            ]})

args_list = submit_utils.get_args_list(
    params_shared_dict=params_shared_dict,
    params_coupled_dict=params_coupled_dict,
)
submit_utils.run_args_list(
    args_list,
    script_name=join(repo_dir, 'experiments', '07_cv_train_model.py'),
    actually_run=True,
    n_cpus=len(os.sched_getaffinity(0)),
)
