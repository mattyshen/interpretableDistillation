from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
import xgboost as xgb
from imodels import FIGSRegressor, FIGSClassifier
from imodels.importance import RandomForestPlusRegressor, RandomForestPlusClassifier

from interpretDistill.fourierDistill import FTDistillRegressorCV, FTDistillClassifierCV
from interpretDistill.featurizer import RegFeaturizer, ClassFeaturizer, GMMBinaryMapper
from interpretDistill.tabdl import TabDLM

def get_params(task_type, model_name, args):
    if task_type == 'regression':
        if model_name == 'featurizer':
            params = ['bit', 'depth']
        if model_name == 'gmm_binary_mapper':
            params = []
        elif model_name == 'random_forest':
            params = ['max_depth', 'max_features']
        elif model_name == 'rf_plus':
            model = RandomForestPlusRegressor(rf_model=rf_model)
            params = ['max_depth', 'max_features']
        elif model_name == 'figs':
            params = ['max_rules', 'max_trees','max_features']
        elif model_name == 'xgboost':
            params = ['max_depth']
        elif model_name == 'resnet':
            params = []
        elif model_name == 'ft_transformer':
            params = []
        elif model_name == 'ft_distill': 
            params = ['pre_interaction', 'pre_max_features', 'post_interaction', 'post_max_features']
        else:
            params = []
        return  params
    elif task_type in ['binary', 'multiclass', 'classification']:
        if model_name == 'featurizer':
            model = ClassFeaturizer(depth=args.depth, bit=args.bit)
        elif model_name == 'random_forest':
            model = RandomForestClassifier(max_depth=args.max_depth, min_samples_leaf=5, max_features=args.max_features)
        elif model_name == 'rf_plus':
            rf_model = RandomForestClassifier(max_depth=args.max_depth, min_samples_leaf=5, max_features=args.max_features)
            model = RandomForestPlusClassifier(rf_model=rf_model)
        elif model_name == 'figs':
            model = FIGSClassifier(max_rules=args.max_rules, max_trees=args.max_trees, max_features=args.max_features)
        elif model_name == 'xgboost':
            model = xgb.XGBClassifier(max_depth=args.max_depth)
        elif model_name == 'resnet':
            model = TabDLM(model_type='ResNet', 
                 task_type=task_type,
                 gpu=args.gpu,
                 n_classes=args.n_classes,
                 n_epochs=args.n_epochs)
        elif model_name == 'ft_transformer':
            model = TabDLM(model_type='FTTransformer', 
                 task_type=task_type,
                 gpu=args.gpu,
                 n_classes=args.n_classes,
                 n_epochs=args.n_epochs)
        elif model_name == 'ft_distill': 
            model = FTDistillClassifierCV(pre_interaction=args.pre_interaction, pre_max_features=args.pre_max_features,
                 post_interaction=args.post_interaction, post_max_features=args.post_max_features, size_interactions=args.size_interactions)
        else:
            model = None
        return model
    else:
        raise ValueError('Invalid task_type: {}'.format(task_type))
        return None