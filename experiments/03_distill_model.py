import argparse
from copy import deepcopy
import logging
import random
from collections import defaultdict
from os.path import join
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score, r2_score
from sklearn.model_selection import train_test_split
import joblib
import imodels
import inspect
import os.path
import sys
import imodelsx.cache_save_utils

path_to_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.append(path_to_repo)

import interpretDistill.model
import interpretDistill.data


def fit_model(model, X_train, y_train, feature_names, r):
    # fit the model
    fit_parameters = inspect.signature(model.fit).parameters.keys()
    if "feature_names" in fit_parameters and feature_names is not None:
        model.fit(X_train, y_train, feature_names=feature_names)
    elif type(model) == imodels.importance.rf_plus.RandomForestPlusRegressor:
        model.fit(X_train, y_train.to_numpy())
    else:
        model.fit(X_train, y_train)

    return r, model


def evaluate_model(model, model_name, comp, task, X_train, X_val, y_train, y_val, r):
    """Evaluate model performance on each split"""
    if task == 'regression':
        metrics = {
            "r2_score": r2_score,
        }
    else:
        metrics = {
            "accuracy": accuracy_score,
        }
    for split_name, (X_, y_) in zip(
        ["train", "val"], [(X_train, y_train), (X_val, y_val)]
    ):
        y_pred_ = model.predict(X_)
        for metric_name, metric_fn in metrics.items():
            r[f"{model_name}_{metric_name}_{split_name}_{comp}"] = metric_fn(y_, y_pred_)

    return r


# initialize args
def add_main_args(parser):
    """Caching uses the non-default values from argparse to name the saving directory.
    Changing the default arg an argument will break cache compatibility with previous runs.
    """

    # dataset args
    parser.add_argument(
        "--dataset_name", 
        type=str, 
        choices=["ca_housing", "abalone", "parkinsons", "airfoil", "cpu_act", "concrete", "powerplant", 
                 "miami_housing", "insurance", "qsar", "allstate", "mercedes", "transaction"],
        default="ca_housing", 
        help="name of dataset"
    )
    parser.add_argument(
        "--subsample_frac", type=float, default=0.25, help="fraction of samples to use for val set"
    )

    # training misc args
    parser.add_argument(
        "--seed", type=int, default=0, help="random seed"
    )
    parser.add_argument(
        "--save_dir",
        type=str,
        default=join(path_to_repo, "results"),
        help="directory for saving",
    )

    # model args
    parser.add_argument(
        "--model_name",
        type=str,
        choices=["random_forest", "figs", "xgboost", "resnet", "ft_transformer", "rf_plus"],
        default="ft_transformer",
        help="name of (teacher, if distillation) model",
    )
    parser.add_argument(
        "--distiller_name",
        type=str,
        choices=["random_forest", "figs", "xgboost", "resnet", "ft_transformer", "rf_plus"],
        default="figs",
        help="name of distiller model",
    )
    parser.add_argument(
        "--max_depth", type=int, default=4, help="max depth of tree based models (RF, XGB)")
    parser.add_argument(
        "--max_rules", type=int, default=60, help="max rules of FIGS model"
    )
    parser.add_argument(
        "--max_trees", type=int, default=30, help="max trees of FIGS model"
    )
    parser.add_argument(
        "--n_epochs", type=int, default=100, help="number of epochs for DL based models"
    )
    parser.add_argument(
        "--gpu", type=int, choices=[0, 1, 2, 3, 4], default=3, help="gpu"
    )
    return parser


def add_computational_args(parser):
    """Arguments that only affect computation and not the results (shouldnt use when checking cache)"""
    parser.add_argument(
        "--use_cache",
        type=int,
        default=1,
        choices=[0, 1],
        help="whether to check for cache",
    )
    return parser


if __name__ == "__main__":
    # get args
    parser = argparse.ArgumentParser()
    parser_without_computational_args = add_main_args(parser)
    parser = add_computational_args(deepcopy(parser_without_computational_args))
    args = parser.parse_args()

    # set up logging
    logger = logging.getLogger()
    logging.basicConfig(level=logging.INFO)

    # set up saving directory + check for cache
    already_cached, save_dir_unique = imodelsx.cache_save_utils.get_save_dir_unique(
        parser, parser_without_computational_args, args, args.save_dir
    )

    if args.use_cache and already_cached:
        logging.info(f"cached version exists! Successfully skipping :)\n\n\n")
        exit(0)
    for k in sorted(vars(args)):
        logger.info("\t" + k + " " + str(vars(args)[k]))
    logging.info(f"\n\n\tsaving to " + save_dir_unique + "\n")

    # set seed
    np.random.seed(args.seed)
    random.seed(args.seed)

    X, y, args = interpretDistill.data.load_tabular_dataset(args.dataset_name, args)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)
    X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=args.subsample_frac, random_state=args.seed)

    # load tabular data
    # https://csinva.io/imodels/util/data_util.html#imodels.util.data_util.get_clean_dataset
    # X_train, X_test, y_train, y_test, feature_names = imodels.get_clean_dataset('compas_two_year_clean', data_source='imodels', test_size=0.33)

    # load model
    model = interpretDistill.model.get_model(args.task_type, args.model_name, args)
    distiller = interpretDistill.model.get_model(args.task_type, args.distiller_name, args)

    # set up saving dictionary + save params file
    r = defaultdict(list)
    r.update(vars(args))
    r["save_dir_unique"] = save_dir_unique
    imodelsx.cache_save_utils.save_json(
        args=args, save_dir=save_dir_unique, fname="params.json", r=r
    )

    feature_names = list(X_train.columns)
    
    # fit
    r, model = fit_model(model, X_train, y_train, feature_names, r)
    y_train_teacher = model.predict(X_train)
    y_train_teacher = pd.Series(y_train_teacher, name = y_train.name)
    r, distiller = fit_model(distiller, X_train, y_train_teacher, feature_names, r)
    X_val
    r = evaluate_model(model, 'teacher', 'true', args.task_type, X_train, X_val, y_train, y_val, r)
    r = evaluate_model(distiller, 'distiller', 'true', args.task_type, X_train, X_val, y_train, y_val, r)
    r = evaluate_model(distiller, 'distiller', 'teacher', args.task_type, X_train, X_val, model.predict(X_train), model.predict(X_val), r)

    # save results
    print(f'save_dir_unique: {save_dir_unique}')
    joblib.dump(
        r, join(save_dir_unique, "results.pkl")
    )  # caching requires that this is called results.pkl
    joblib.dump(model, join(save_dir_unique, "model.pkl"))
    logging.info("Succesfully completed :)\n\n")