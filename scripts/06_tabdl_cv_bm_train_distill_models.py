from imodelsx import submit_utils
from os.path import dirname, join
import os.path
repo_dir = dirname(dirname(os.path.abspath(__file__)))

# Showcasing different ways to sweep over arguments
# Can pass any empty dict for any of these to avoid sweeping

# List of values to sweep over (sweeps over all combinations of these)
params_shared_dict = {
    'seed': [0],
    'save_dir': [join(repo_dir, 'results/06_cv_bm_train_distill_model/tabdl')],
    'use_cache': [1], # pass binary values with 0/1 instead of the ambiguous strings True/False
}

# List of tuples to sweep over (these values are coupled, and swept over together)
# Note: this is a dictionary so you shouldn't have repeated keys

#datasets not completed = ["insurance", "qsar", "allstate", "mercedes", "transaction"]

params_coupled_dict = {}

# #FT, ResNet params
# params_coupled_dict.update({('dataset_name', 
#                              'model_name',
#                              'distiller_name'):
#                             [(dn, mn, distn) 
#                              for dn in ["ca_housing", "abalone", "parkinsons", "airfoil", "cpu_act", "concrete", "powerplant", "miami_housing"]
#                              for mn in ['ft_transformer', 'resnet']
#                              for distn in ['ft_distill', 'figs']
#                             ]})
#still need "parkinsons",
params_coupled_dict.update({('dataset_name', 
                             'model_name',
                             'distiller_name',
                            'n_epochs', 
                            'binary_mapper_depth'):
                            [(dn, mn, distn, ne, 3) 
                             for dn in ["cpu_act", "miami_housing"]
                             for mn in ['ft_transformer']
                             for distn in ['ft_distill', 'figs']
                             for ne in [100, 200]
                            ]})
# params_coupled_dict.update({('dataset_name', 
#                              'model_name',
#                              'distiller_name',
#                              'binary_mapper_name',
#                              'binary_mapper_depth',
#                              'binary_mapper_bit', 
#                             'n_epochs'):
#                             [(dn, mn, distn, 'dt_binary_mapper', bmd, 0, ne)
#                              for dn in ["ca_housing", "abalone", "parkinsons", "airfoil", "cpu_act", "concrete", "powerplant", "miami_housing"]
#                              for mn in ['ft_transformer', 'resnet']
#                              for bmd in [2, 3]
#                              for distn in ["ft_distill", "figs"]
#                              for ne in [100, 200]
#                             ]})
# params_coupled_dict.update({('dataset_name', 
#                              'model_name',
#                              'distiller_name',
#                              'binary_mapper_name',
#                              'binary_mapper_depth',
#                              'binary_mapper_bit', 
#                             'n_epochs'):
#                             [(dn, mn, distn, 'dt_binary_mapper', 3, 0, ne)
#                              for dn in ["cpu_act", "parkinsons", "miami_housing"]
#                              for mn in ['ft_transformer']
#                              for distn in ["ft_distill", "figs"]
#                              for ne in [100, 200]
#                             ]})


# Args list is a list of dictionaries
# If you want to do something special to remove some of these runs, can remove them before calling run_args_list
args_list = submit_utils.get_args_list(
    params_shared_dict=params_shared_dict,
    params_coupled_dict=params_coupled_dict,
)
submit_utils.run_args_list(
    args_list,
    script_name=join(repo_dir, 'experiments', '06_cv_bm_train_distill_model.py'),
    actually_run=True,
    n_cpus=len(os.sched_getaffinity(0)),
)
