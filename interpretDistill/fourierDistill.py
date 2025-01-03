import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sklearn.linear_model import Ridge, RidgeCV, MultiTaskElasticNetCV
from celer import Lasso, ElasticNet, ElasticNetCV, LogisticRegression
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.preprocessing import PolynomialFeatures
from sklearn.metrics import accuracy_score

from imodels.util.arguments import check_fit_arguments
#from interpretDistill.figs_d import FIGSRegressorCV, FIGSRegressor
from imodels import FIGSRegressor

import sys
import os
import time
import copy

#print(os.getcwd())
sys.path.append('/home/mattyshen/interpretableDistillation/')

from interpretDistill.subset_predictors import *
#from subset_predictors import *

sys.path.append('/home/mattyshen/qsft-dev/src/')

from qsft.wrapper import sparse_transform

class FTFIGS:
    def __init__(self,
                figs = FIGSRegressor(),
                noise_sd = 0,
                max_interactions=-1,
                max_interaction_size=-1):
        self.figs = figs
        self.no_interaction = []
        self.noise_sd = noise_sd
        self.max_interactions = max_interactions
        self.max_interaction_size = max_interaction_size
        
    def _traverse_paths(self, node):
        if node is None:
            return []
        paths = []
        vals = []
        def dfs(current, path):
            if current.left is None and current.right is None:
                paths.append(copy.deepcopy(path))
                vals.append(current.value.item())
                return 
            if current.right:
                path.append((current, 'flip'))
                dfs(current.right, path)
                path.pop()
            if current.left:
                path.append((current, 'original'))
                dfs(current.left, path)
                path.pop()
        dfs(node, [])
        return list(zip(paths, vals))

    def _traverse_and_collect(self, node, feature_threshold_pairs):
        if node is None:
            return
        if (node.right is not None and node.left is not None) and node.threshold is not None:
            feature_threshold_pairs.append((node.feature_names[node.feature], node.threshold))

        self._traverse_and_collect(node.left, feature_threshold_pairs)
        self._traverse_and_collect(node.right, feature_threshold_pairs)
        
    def _collect_interactions(self, figs_paths):
        interactions = []
        figs_weight_dict = {}
        for i, tree in enumerate(figs_paths):
                for interaction_weight in tree:
                    interaction, weight = interaction_weight
                    cur_interaction = []
                    for rule, sign in interaction:
                        if sign == 'original':
                            cur_interaction.append(f'{rule.feature_names[rule.feature]}_<=_{str(round(rule.threshold, 3))}')
                        else:
                            cur_interaction.append(f'{rule.feature_names[rule.feature]}_>_{str(round(rule.threshold, 3))}')
                    figs_weight_dict[tuple(cur_interaction)] = weight
                    interactions.append([cur_interaction, weight])
        self.interactions = interactions
        self.interaction_weights = figs_weight_dict
    
    def _fit_figs(self, X, y):
        print('fitting figs')
        self.figs.fit(X, y)
        feature_threshold_pairs = []
        figs_rules = []
        if hasattr(self.figs, 'trees_'):
            trees = self.figs.trees_
        else:
            trees = self.figs.figs.trees_
        
        print('collection')
        for tree in trees:
            self._traverse_and_collect(tree, feature_threshold_pairs)
            figs_rules.append(self._traverse_paths(tree))
            
        self.f_t_pairings = feature_threshold_pairs
        
        self.figs_rules = figs_rules
        self._collect_interactions(self.figs_rules)
        
        self.num_interactions = len([path for tree in self.figs_rules for path in tree])
        if self.max_interactions < 0:
            self.max_interactions = self.num_interactions
        if self.max_interaction_size  < 0:
            self.max_interaction_size = max([len(path) for path, weight in self.interactions])
    def _transform(self, X, y):
        transformed_features = []
        
        for f, t in self.f_t_pairings:
            transformed_features.append(pd.Series(X[f] <= round(t, 3), name = f'{f}_<=_{str(round(t, 3))}'))
            transformed_features.append(pd.Series(X[f] > round(t, 3), name = f'{f}_>_{str(round(t, 3))}'))
            self.no_interaction.append(set([f'{f}_<=_{str(round(t, 3))}', f'{f}_>_{str(round(t, 3))}']))
        
        X_bin = pd.concat(transformed_features, axis=1).astype(int).replace({-1:0, 0:0, 1:1}).set_index([X.index])
        X_bin = X_bin.loc[:,~X_bin.columns.duplicated()].copy()
        return X_bin
    
    def subsample(self, indices: list):
        binary_array = self.X.to_numpy()
        
        x_array = np.array(binary_array @ (1 << np.arange(binary_array.shape[1]-1, -1, -1)))
        y_array = np.array(self.y)

        x_to_mean_y = pd.DataFrame({'idx': x_array, 'y': y_array}).groupby('idx').mean().reset_index()
        #print(x_to_mean_y)
        query_true = pd.merge(pd.DataFrame({'idx': indices}), x_to_mean_y, how='left', on='idx')
        #print(query_true)
        missing_true = query_true[query_true['y'].isna()]['idx'].to_numpy()
        print(f'number of true y: {len(indices) - len(missing_true)}')
        X_missing = pd.DataFrame(((missing_true[:, None] & (1 << np.arange(self.dim)[::-1])) > 0).astype(int), columns = self.X.columns)
        query_hat = pd.DataFrame({'idx': missing_true, 'y': self.figs_lm_predict(X_missing)})
        print(f'number of figs y: {len(missing_true)}')
        print('----')
        query = pd.merge(query_true, query_hat, on='idx', how='left', suffixes=('', '_sub'))
        query['y'] = query['y'].combine_first(query['y_sub'])
        query = query.drop(columns=['y_sub'])
    
        # query['idx'] = pd.Categorical(query['idx'], categories=indices, ordered=True)
        # query.sort_values('idx', inplace=True)

        return query['y'].to_list()
        
        
    def fit(self, X, y):
        print('_fit_figs')
        self._fit_figs(X, y)
        print('transform')
        self.X = self._transform(X, y)
        self.y = y
        print('qsft')
        self.dim = self.X.shape[1]
        self.qsft = sparse_transform(self.subsample, 
                         q = 2, 
                         n = self.dim,
                         b = int(np.ceil(np.log2(self.max_interactions))),
                         max_degree = self.max_interaction_size,
                         noise_sd = self.noise_sd,
                         num_subsample=4, 
                         num_repeat=4)
        
    def _make_figs_lm_df(self, X):
        #X has to be figs discretized (with _transform)
        df = pd.DataFrame()
        for interaction, weight in self.interactions:
            cur_val = 1
            for inter in interaction:
                cur_val *= X[inter]
            df[tuple(interaction)] = cur_val.values
        return df
        
    def figs_lm_predict(self, X):
        X_inter = self._make_figs_lm_df(X)
        #X has to be figs discretized (with _transform)
        # pred_sum = 0 
        # for interaction in self.interaction_weights.keys():
        #     pred_sum += self.interaction_weights[interaction] * X[interaction]
        # return pred_sum
        beta_figs = np.array([self.interaction_weights[c] for c in X_inter.columns])
        return list((X_inter.to_numpy()@beta_figs).reshape(-1, ))
        
    def predict(self):
        print('hello')

class FTDistill:
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0,
                 pre_lam2=1.0,
                 pre_max_features=0.1,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=0.1,
                 size_interactions=3,
                 mo=False,
                 re_fit_alpha=None):
        
        self.pre_interaction = pre_interaction
        self.pre_lam1 = pre_lam1
        self.pre_lam2 = pre_lam2
        self.pre_max_features = pre_max_features
        self.post_interaction = post_interaction
        self.post_lam1 = post_lam1
        self.post_lam2 = post_lam2
        self.post_max_features = post_max_features
        self.size_interactions = size_interactions
        self.re_fit_alpha = re_fit_alpha
        self.post_sparsity_model = Ridge(alpha=self.re_fit_alpha, fit_intercept=False)
        self.mo = mo
        
        #TODO: build in iRF, L0
        if self.pre_interaction == 'l1':
            self.pre_interaction_model = ElasticNet(alpha=self.pre_lam1, l1_ratio=1)
        elif self.pre_interaction == 'l1l2':
            assert self.pre_lam2 is not None, "Pre-interaction l1l2 based models require `pre_lam22` argument"
            self.pre_interaction_model = ElasticNet(alpha=self.pre_lam1 + self.pre_lam2, l1_ratio=self.pre_lam1 / (self.pre_lam1 + self.pre_lam2))
        elif self.pre_interaction == 'l0':
            assert self.pre_max_features is not None, "Pre-interaction l0 based models require `pre_max_features` argument"
            self.pre_interaction_model = L0Regressor(max_support_size=self.pre_max_features)
        elif self.pre_interaction == 'l0l2':
            assert self.pre_max_features is not None, "Pre-interaction l0l2 based models require `pre_max_features` argument"
            assert self.pre_lam2 is not None, "Pre-interaction l0l2 based models require `pre_lam22` argument"
            #TODO: add arguments for overall model for L0Regressor
            self.pre_interaction_model = L0L2Regressor(max_support_size = self.pre_max_features)
        else:
            self.pre_interaction_model = None
            
        if self.post_interaction == 'l1':
            self.post_interaction_model = ElasticNet(alpha=self.post_lam1, l1_ratio=1, fit_intercept=True)
        elif self.post_interaction == 'l0':
            assert self.post_max_features is not None, "l0 based models require `post_max_features` argument"
            self.post_interaction_model = L0Regressor(max_support_size=self.post_max_features)
        elif self.post_interaction == 'l1l2':
            assert self.post_lam2 is not None, "Post-interaction l1l2 based models require `post_lam22` argument"
            self.post_interaction_model = ElasticNet(alpha=self.post_lam1 + self.post_lam2, l1_ratio=self.post_lam1 / (self.post_lam1 + self.post_lam2), fit_intercept=True)
        elif self.post_interaction == 'l0l2':
            assert self.post_lam2 is not None, "Post-interaction l0l2 based models require `post_lam22` argument"
            assert self.post_max_features is not None, "l0l2 based models require `post_max_features` argument"
            #TODO: add arguments for overall model for L0Regressor
            self.post_interaction_model = L0L2Regressor(max_support_size = self.post_max_features)
        else:
            self.post_interaction_model = ElasticNet(alpha=self.post_lam1 + self.post_lam2, l1_ratio=self.post_lam1 / (self.post_lam1 + self.post_lam2), fit_intercept=True)
            
    def fit(self, X, y, no_interaction=[]):
        """
        Train the model using the training data.

        Parameters:
        X : DataFrame, shape (n_samples, n_features)
            Training data.
        y : array-like, shape (n_samples,)
            Target values.
        no_interaction : list of sets
            List of feature sets that should not interact.

        Returns:
        self : object
            Returns the instance itself.
        """
        X.columns = [s.replace(" ", "_") for s in X.columns]
        
        print(f'original X shape: {X.shape, y.shape}')

        self.no_interaction = no_interaction
        if self.pre_interaction_model is not None:
            self.pre_interaction_model.fit(X, y)
            self.pre_interaction_features = X.columns[self.pre_interaction_model.coef_ != 0]
            X = X[self.pre_interaction_features]
            #print(f'Selected features: {self.pre_interaction_features}')
            
            print(f'pre interaction X shape: {X.shape, y.shape}')

        self.poly = PolynomialFeatures(degree=self.size_interactions, interaction_only=True)
        self.poly.fit(X)

        poly_features = list(map(lambda s: set(s.split()), self.poly.get_feature_names_out(X.columns)))
        
        self.features = [all([len(pot_s.intersection(s)) < 2 for s in self.no_interaction]) for pot_s in poly_features]
        
        Chi = pd.DataFrame(self.poly.transform(X), columns=list(map(lambda f: tuple(f), poly_features))).loc[:, self.features]
        
        print(f'Chi shape: {Chi.shape}')
        
        Chi.drop(columns = [('1',)], inplace=True)
        print(self.post_interaction_model)
        self.post_interaction_model.fit(Chi, y)
        
        if not self.mo:
            self.post_interaction_features = Chi.columns[self.post_interaction_model.coef_ != 0]
        
        if self.re_fit_alpha is None or self.mo:
            self.post_sparsity_model = self.post_interaction_model
        else:
            Chi[('1',)] = 1
            Chi_post_sparsity = Chi.loc[:, list(np.array([('1',)]+list(self.post_interaction_features), dtype=object))]
            self.post_sparsity_model.fit(Chi_post_sparsity, y)
        
        return self
    
    def predict(self, X):
        """
        Predict using the trained model.

        Parameters:
        X : DataFrame, shape (n_samples, n_features)
            Test data.

        Returns:
        y_pred : array-like, shape (n_samples,)
            Predicted target values.
        """
        if self.pre_interaction_model is not None:
            X = X[self.pre_interaction_features]
            
        poly_features = list(map(lambda s: set(s.split()), self.poly.get_feature_names_out(X.columns)))
        
        Chi = pd.DataFrame(self.poly.transform(X), columns=list(map(lambda f: tuple(f), poly_features))).loc[:, self.features]
        
        Chi.drop(columns = [('1',)], inplace=True)

        if self.re_fit_alpha is not None and not self.mo:
            Chi[('1',)] = 1
            Chi = Chi[np.array([('1',)]+list(self.post_interaction_features), dtype=object)]
        
        return self.post_sparsity_model.predict(Chi)

class FTDistillRegressor(FTDistill):
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0, 
                 pre_lam2=1.0,
                 pre_max_features=0.1,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=0.1,
                 size_interactions=3,
                 mo=False,
                 re_fit_alpha=None):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, mo, re_fit_alpha)
    
class FTDistillRegressorCV(FTDistillRegressor):
    #TODO: let users set alphas to search over for elasticnetCV models (currenly autoset, regardless of lam1/lam2 arguments)
    def __init__(self, 
                 pre_interaction='l0l2', 
                 pre_lam1=0.1, 
                 pre_lam2=0.1,
                 pre_max_features=0.1,
                 post_interaction='l0l2', 
                 post_lam1=0.1, 
                 post_lam2=0.1,
                 post_max_features=30,
                 size_interactions=3,
                 mo=False,
                 re_fit_alpha=[0.1, 1.0, 10],
                 cv=3):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, mo, re_fit_alpha)
        self.cv = cv
        self.post_sparsity_model = RidgeCV(alphas=re_fit_alpha, fit_intercept=False)
        
        #TODO: build in iRF, L0
        if self.pre_interaction == 'l1':
            self.pre_interaction_model = ElasticNetCV(l1_ratio=1, cv=self.cv, max_epochs=5000, n_alphas=10, tol=0.01)
        elif self.pre_interaction == 'l1l2':
            self.pre_interaction_model = ElasticNetCV(l1_ratio=0.5, cv=self.cv, max_epochs=5000, n_alphas=10, tol=0.01)
        elif self.pre_interaction == 'l0':
            assert self.pre_max_features is not None, "Pre-interaction l0 based models require `pre_max_features` argument"
            raise NotImplementedError("l0 pre-interaction selection not implemented")
        elif self.pre_interaction == 'l0l2':
            assert self.pre_max_features is not None, "Pre-interaction l0l2 based models require `pre_max_features` argument"
            assert self.pre_lam2 is not None, "Pre-interaction l0l2 based models require `pre_lam22` argument"
            #TODO: pass in proper arguments
            self.pre_interaction_model = L0L2RegressorCV(max_support_size = self.pre_max_features, cv=self.cv)
        elif self.pre_interaction == 'newl0l2':
            assert self.pre_max_features is not None, "Pre-interaction l0l2 based models require `pre_max_features` argument"
            assert self.pre_lam2 is not None, "Pre-interaction l0l2 based models require `pre_lam22` argument"
            #TODO: pass in proper arguments
            self.pre_interaction_model = NewL0L2RegressorCV(max_support_size = self.pre_max_features, cv=self.cv)
        else:
            self.pre_interaction_model = None
            
        if self.post_interaction == 'l1':
            self.post_interaction_model = ElasticNetCV(l1_ratio=1, cv=self.cv, fit_intercept=True, max_epochs=5000, n_alphas=10, tol=0.01)
        elif self.post_interaction == 'l0':
            assert self.post_max_features is not None, "l0 based models require `post_max_features` argument"
            raise NotImplementedError("l0 interaction selection not implemented")
        elif self.post_interaction == 'l1l2':
            assert self.post_lam2 is not None, "Post-interaction l1l2 based models require `post_lam22` argument"
            if mo:
                self.post_interaction_model = MultiTaskElasticNetCV(l1_ratio=0.5, cv=self.cv, fit_intercept=True, max_iter=100, n_alphas=10, tol = 0.01)
            else:
                self.post_interaction_model = ElasticNetCV(l1_ratio=0.5, cv=self.cv, fit_intercept=True, max_epochs=5000, n_alphas=10, tol = 0.01)
        elif self.post_interaction == 'l0l2':
            assert self.post_lam2 is not None, "Post-interaction l0l2 based models require `post_lam22` argument"
            assert self.post_max_features is not None, "l0l2 based models require `post_max_features` argument"
            if self.mo:
                self.post_interaction_model = MultiOutputRegressor(L0L2RegressorCV(max_support_size = self.post_max_features, cv=self.cv), n_jobs=5)
            else:
                self.post_interaction_model = L0L2RegressorCV(max_support_size = self.post_max_features, cv=self.cv)
        # elif self.post_interaction == 'newl0l2':
        #     assert self.post_lam2 is not None, "Post-interaction l0l2 based models require `post_lam22` argument"
        #     assert self.post_max_features is not None, "l0l2 based models require `post_max_features` argument"
        #     self.post_interaction_model = NewL0L2RegressorCV(max_support_size = self.post_max_features, cv=self.cv)
        else:
            self.post_interaction_model = ElasticNetCV(l1_ratio=0.5, cv=self.cv, fit_intercept=True, max_epochs=5000, n_alphas=10, tol=0.01)

    def fit(self, X, y, no_interaction=[]):
        """
        Train the model using the training data.

        Parameters:
        X : DataFrame, shape (n_samples, n_features)
            Training data.
        y : array-like, shape (n_samples,)
            Target values.
        no_interaction : list of sets
            List of feature sets that should not interact.

        Returns:
        self : object
            Returns the instance itself.
        """
        s = super().fit(X, y, no_interaction)
        
        if not self.mo:
            if self.pre_interaction_model is not None:
                self.pre_lam1 = self.pre_interaction_model.l1_ratio_ * self.pre_interaction_model.alpha_
                self.pre_lam2 = self.pre_interaction_model.alpha_ - self.pre_lam1

            self.post_lam1 = self.post_interaction_model.l1_ratio_ * self.post_interaction_model.alpha_
            self.post_lam2 = self.post_interaction_model.alpha_ - self.post_lam1

            if self.re_fit_alpha is not None:
                self.re_fit_alpha = self.post_sparsity_model.alpha_
        
        return s

class FTDistillClassifier(FTDistill):
    #NOTE THAT FEATURE SELECTION IS DONE WITH REGRESSION, DESPITE THE TASK IS INTENDED TO BE CLASSIFICATION
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0, 
                 pre_lam2=1.0,
                 pre_max_features=0.1,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=0.1,
                 size_interactions=3,  
                 re_fit_alpha=1.0):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, re_fit_alpha)
        
        self.post_sparsity_model = LogisticRegression(C=1/re_fit_alpha, fit_intercept=False)
    
class FTDistillClassifierCV(FTDistillRegressorCV):
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=0.1, 
                 pre_lam2=0.1,
                 pre_max_features=0.1,
                 post_interaction='l1', 
                 post_lam1=0.1, 
                 post_lam2=0.1,
                 post_max_features=0.1,
                 size_interactions=3,  
                 re_fit_alpha=[0.1, 1.0, 10],
                 cv=3):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, False, re_fit_alpha, cv)

        self.post_sparsity_model = LogisticRegression(C=1/re_fit_alpha[0], fit_intercept=False)

    def fit(self, X, y=None, no_interaction=[]):
        self.no_interaction = no_interaction
        if self.pre_interaction_model is not None:
            self.pre_interaction_model.fit(X, y)
            self.pre_interaction_features = X.columns[self.pre_interaction_model.coef_ != 0]
            X = X[self.pre_interaction_features]
            #print(f'Selected features: {self.pre_interaction_features}')

        self.poly = PolynomialFeatures(degree=self.size_interactions, interaction_only=True)
        self.poly.fit(X)

        poly_features = list(map(lambda s: set(s.split()), self.poly.get_feature_names_out(X.columns)))
        
        self.features = [all([len(pot_s.intersection(s)) < 2 for s in self.no_interaction]) for pot_s in poly_features]
        
        Chi = pd.DataFrame(self.poly.transform(X), columns=list(map(lambda f: tuple(f), poly_features))).loc[:, self.features]

        #print('Post-interaction model fitting')
        #print(Chi.shape)
        
        Chi.drop(columns = [('1',)], inplace=True)

        self.post_interaction_model.fit(Chi, y)
        
        if self.pre_interaction_model is not None:
            self.pre_lam1 = self.pre_interaction_model.l1_ratio_ * self.pre_interaction_model.alpha_
            self.pre_lam2 = self.pre_interaction_model.alpha_ - self.pre_lam1
            
        self.post_lam1 = self.post_interaction_model.l1_ratio_ * self.post_interaction_model.alpha_
        self.post_lam2 = self.post_interaction_model.alpha_ - self.post_lam1
        
        self.post_interaction_features = Chi.columns[self.post_interaction_model.coef_ != 0]

        #print('Re-fitting with LogisticRegression with L1 penalty')
        Chi[('1',)] = 1
        Chi_post_sparsity = Chi[np.array([('1',)]+list(self.post_interaction_features), dtype=object)]
        
        self.scores_ = [[] for _ in self.re_fit_alpha]
        kf = KFold(n_splits=self.cv, shuffle=True, random_state=405)

        for i, (train_index, test_index) in enumerate(kf.split(Chi_post_sparsity)):
            Chi_post_sparsity_out, y_out = Chi_post_sparsity.iloc[test_index, :], y.iloc[test_index]
            Chi_post_sparsity_in, y_in = Chi_post_sparsity.iloc[train_index, :], y.iloc[train_index]
            for i, reg_param in enumerate(self.re_fit_alpha):
                base_est = LogisticRegression(C = 1/reg_param, penalty='l1', max_epochs=50000, max_iter=50)
                base_est.fit(Chi_post_sparsity_in, y_in)
                self.scores_[i].append(accuracy_score(y_out, base_est.predict(Chi_post_sparsity_out)))
        self.scores_ = [np.mean(s) for s in self.scores_]

        self.re_fit_alpha = self.re_fit_alpha[np.argmax(self.scores_)]
        self.post_sparsity_model = LogisticRegression(C = 1/self.re_fit_alpha, penalty='l1', max_epochs=5000, max_iter=100)
        self.post_sparsity_model.fit(Chi_post_sparsity, y)
        
        return self
    
   