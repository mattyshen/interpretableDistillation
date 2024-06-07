import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import l0learn
import l0bnb
from sklearn.linear_model import Ridge, RidgeCV
from celer import Lasso, ElasticNet, ElasticNetCV, LogisticRegression
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.preprocessing import PolynomialFeatures

from imodels.util.arguments import check_fit_arguments

import sys
import os
import time

class FTDistill:
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0,
                 pre_lam2=1.0,
                 pre_max_features=None,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=None,
                 size_interactions=2,  
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
        
        #TODO: build in iRF, L0
        if self.pre_interaction == 'l1':
            self.pre_interaction_model = ElasticNet(alpha=self.pre_lam1, l1_ratio=1, fit_intercept=False)
        elif self.pre_interaction == 'l1l2':
            assert self.pre_lam2 is not None, "Pre-interaction l1l2 based models require `pre_lam22` argument"
            self.pre_interaction_model = ElasticNet(alpha=self.pre_lam1 + self.pre_lam2, l1_ratio=self.pre_lam1 / (self.pre_lam1 + self.pre_lam2), fit_intercept=False)
        elif self.pre_interaction == 'l0':
            assert self.pre_max_features is not None, "Pre-interaction l0 based models require `pre_max_features` argument"
            raise NotImplementedError("l0 pre-interaction selection not implemented")
        elif self.pre_interaction == 'l0l2':
            assert self.pre_max_features is not None, "Pre-interaction l0l2 based models require `pre_max_features` argument"
            assert self.pre_lam2 is not None, "Pre-interaction l0l2 based models require `pre_lam22` argument"
            raise NotImplementedError("l0l2 pre-interaction selection not implemented")
        else:
            self.pre_interaction_model = None
            
        if self.post_interaction == 'l1':
            self.post_interaction_model = ElasticNet(alpha=self.post_lam1, l1_ratio=1, fit_intercept=False)
        elif self.post_interaction == 'l0':
            assert self.max_features is not None, "l0 based models require `post_max_features` argument"
            raise NotImplementedError("l0 interaction selection not implemented")
        elif self.post_interaction == 'l1l2':
            assert self.post_lam2 is not None, "Post-interaction l1l2 based models require `post_lam22` argument"
            self.post_interaction_model = ElasticNet(alpha=self.post_lam1 + self.post_lam2, l1_ratio=self.post_lam1 / (self.post_lam1 + self.post_lam2), fit_intercept=False)
        elif self.post_interaction == 'l0l2':
            assert self.post_lam2 is not None, "Post-interaction l0l2 based models require `post_lam22` argument"
            assert self.max_features is not None, "l0l2 based models require `post_max_features` argument"
            raise NotImplementedError("l0l2 interaction selection not implemented")
        else:
            self.post_interaction_model = ElasticNet(alpha=self.post_lam1 + self.post_lam2, l1_ratio=self.post_lam1 / (self.post_lam1 + self.post_lam2), fit_intercept=False)
            
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
        
        self.no_interaction = no_interaction
        if self.pre_interaction_model is not None:
            self.pre_interaction_model.fit(X, y)
            self.pre_interaction_features = X.columns[self.pre_interaction_model.coef_ != 0]
            X = X[self.pre_interaction_features]
            print(f'Selected features: {self.pre_interaction_features}')

        self.poly = PolynomialFeatures(degree=self.size_interactions, interaction_only=True)
        self.poly.fit(X)

        poly_features = list(map(lambda s: set(s.split()), self.poly.get_feature_names_out(X.columns)))
        
        self.features = [all([len(pot_s.intersection(s)) < 2 for s in self.no_interaction]) for pot_s in poly_features]
        
        Chi = pd.DataFrame(self.poly.transform(X), columns=list(map(lambda f: tuple(f), poly_features))).loc[:, self.features]

        print('Post-interaction model fitting')
        print(Chi.shape)
        
        self.post_interaction_model.fit(Chi, y)
        if hasattr(self.post_interaction_model, 'l1_ratio_'):
            self.post_lam1 = self.post_interaction_model.l1_ratio_ * self.post_interaction_model.alpha_
            self.post_lam2 = self.post_interaction_model.alpha_ - self.post_lam1
        else:
            self.post_lam1 = self.post_interaction_model.l1_ratio * self.post_interaction_model.alpha
            self.post_lam2 = self.post_interaction_model.alpha - self.post_lam1
        self.post_interaction_features = Chi.columns[self.post_interaction_model.coef_ != 0]

        if self.re_fit_alpha is not None:
            print('Re-fitting with Ridge regression')
            Chi_post_sparsity = Chi[self.post_interaction_features]
            self.post_interaction_model = self.post_sparsity_model
            self.post_interaction_model.fit(Chi_post_sparsity, y)
        
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

        if self.re_fit_alpha is not None:
            Chi = Chi[self.post_interaction_features]
        
        return self.post_interaction_model.predict(Chi)

class FTDistillRegressor(FTDistill):
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0, 
                 pre_lam2=1.0,
                 pre_max_features=None,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=None,
                 size_interactions=2,  
                 re_fit_alpha=None):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, re_fit_alpha)

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
        return super().fit(X, y, no_interaction)

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
        return super().predict(X)
    
class FTDistillRegressorCV(FTDistillRegressor):
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0, 
                 pre_lam2=1.0,
                 pre_max_features=None,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=None,
                 size_interactions=2,  
                 re_fit_alpha=[0.1, 1.0, 10],
                 cv=3):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, re_fit_alpha)
        self.cv = cv
        self.post_sparsity_model = RidgeCV(alphas=re_fit_alpha, fit_intercept=False)
        
        #TODO: build in iRF, L0
        if self.pre_interaction == 'l1':
            self.pre_interaction_model = ElasticNetCV(l1_ratio=1, cv = self.cv, fit_intercept=False, max_epochs = 5000, n_alphas = 10, tol = 0.01)
        elif self.pre_interaction == 'l1l2':
            self.pre_interaction_model = ElasticNetCV(l1_ratio=0.5, cv = self.cv, fit_intercept=False, max_epochs = 5000, n_alphas = 10, tol = 0.01)
        elif self.pre_interaction == 'l0':
            assert self.pre_max_features is not None, "Pre-interaction l0 based models require `pre_max_features` argument"
            raise NotImplementedError("l0 pre-interaction selection not implemented")
        elif self.pre_interaction == 'l0l2':
            assert self.pre_max_features is not None, "Pre-interaction l0l2 based models require `pre_max_features` argument"
            assert self.pre_lam2 is not None, "Pre-interaction l0l2 based models require `pre_lam22` argument"
            raise NotImplementedError("l0l2 pre-interaction selection not implemented")
        else:
            self.pre_interaction_model = None
            
        if self.post_interaction == 'l1':
            self.post_interaction_model = ElasticNetCV(l1_ratio=1, cv = self.cv, fit_intercept=False, max_epochs = 5000, n_alphas = 10, tol = 0.01)
        elif self.post_interaction == 'l0':
            assert self.max_features is not None, "l0 based models require `post_max_features` argument"
            raise NotImplementedError("l0 interaction selection not implemented")
        elif self.post_interaction == 'l1l2':
            assert self.post_lam2 is not None, "Post-interaction l1l2 based models require `post_lam22` argument"
            self.post_interaction_model = ElasticNetCV(l1_ratio=0.5, cv = self.cv, fit_intercept=False, max_epochs = 5000, n_alphas = 10, tol = 0.01)
        elif self.post_interaction == 'l0l2':
            assert self.post_lam2 is not None, "Post-interaction l0l2 based models require `post_lam22` argument"
            assert self.max_features is not None, "l0l2 based models require `post_max_features` argument"
            raise NotImplementedError("l0l2 interaction selection not implemented")
        else:
            self.post_interaction_model = ElasticNetCV(l1_ratio=0.5, cv = self.cv, fit_intercept=False, max_epochs = 5000, n_alphas = 10, tol = 0.01)

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
        
        if self.pre_interaction_model is not None:
            self.pre_lam1 = self.pre_interaction_model.l1_ratio_ * self.pre_interaction_model.alpha_
            self.pre_lam2 = self.pre_interaction_model.alpha_ - self.pre_lam1
        
        if self.re_fit_alpha is not None:
            self.re_fit_alpha = self.post_interaction_model.alpha_
        
        return s

class FTDistillClassifier(FTDistill):
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0, 
                 pre_lam2=1.0,
                 pre_max_features=None,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=None,
                 size_interactions=2,  
                 re_fit_alpha=1.0):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, re_fit_alpha)
        
        self.post_sparsity_model = LogisticRegression(C=1/re_fit_alpha, fit_intercept=False)
    
class FTDistillClassifierCV(FTDistillRegressorCV):
    def __init__(self, 
                 pre_interaction='l1', 
                 pre_lam1=1.0, 
                 pre_lam2=1.0,
                 pre_max_features=None,
                 post_interaction='l1', 
                 post_lam1=1.0, 
                 post_lam2=1.0,
                 post_max_features=None,
                 size_interactions=2,  
                 re_fit_alpha=[0.1, 1.0, 10],
                 cv=3):
        super().__init__(pre_interaction, pre_lam1, pre_lam2, pre_max_features, 
                         post_interaction, post_lam1, post_lam2, post_max_features, 
                         size_interactions, re_fit_alpha, cv)

        self.post_sparsity_model = LogisticRegression(C=1/re_fit_alpha[0], fit_intercept=False)

    def fit(self, X, y=None, no_interaction=[]):
        self.no_interaction = no_interaction
        if self.pre_interaction_model is not None:
            self.pre_interaction_model.fit(X, y)
            self.pre_interaction_features = X.columns[self.pre_interaction_model.coef_ != 0]
            X = X[self.pre_interaction_features]
            print(f'Selected features: {self.pre_interaction_features}')

        self.poly = PolynomialFeatures(degree=self.size_interactions, interaction_only=True)
        self.poly.fit(X)

        poly_features = list(map(lambda s: set(s.split()), self.poly.get_feature_names_out(X.columns)))
        
        self.features = [all([len(pot_s.intersection(s)) < 2 for s in self.no_interaction]) for pot_s in poly_features]
        
        Chi = pd.DataFrame(self.poly.transform(X), columns=list(map(lambda f: tuple(f), poly_features))).loc[:, self.features]

        print('Post-interaction model fitting')
        print(Chi.shape)

        self.post_interaction_model.fit(Chi, y)
        if hasattr(self.post_interaction_model, 'l1_ratio_'):
            self.post_lam1 = self.post_interaction_model.l1_ratio_ * self.post_interaction_model.alpha_
            self.post_lam2 = self.post_interaction_model.alpha_ - self.post_lam1
        else:
            self.post_lam1 = self.post_interaction_model.l1_ratio * self.post_interaction_model.alpha
            self.post_lam2 = self.post_interaction_model.alpha - self.post_lam1
        self.post_interaction_features = Chi.columns[self.post_interaction_model.coef_ != 0]

        print('Re-fitting with LogisticRegression with L1 penalty')
        Chi_post_sparsity = Chi[self.post_interaction_features]
        
        self.scores_ = [[] for _ in self.re_fit_alpha]
        kf = KFold(n_splits=self.cv, shuffle = True, random_state = 405)

        for i, (train_index, test_index) in enumerate(kf.split(Chi_post_sparsity)):
            Chi_post_sparsity_out, y_out = Chi_post_sparsity.iloc[test_index, :], y.iloc[test_index]
            Chi_post_sparsity_in, y_in = Chi_post_sparsity.iloc[train_index, :], y.iloc[train_index]
            for i, reg_param in enumerate(self.re_fit_alpha):
                base_est = LogisticRegression(C = 1/reg_param, penalty = 'l1', max_epochs = 50000, max_iter=50)
                base_est.fit(Chi_post_sparsity_in, y_in)
                self.scores_[i].append(np.mean(base_est.predict(Chi_post_sparsity_out) == y_out))
        self.scores_ = [np.mean(s) for s in self.scores_]

        self.re_fit_alpha = self.re_fit_alpha[np.argmax(self.scores_)]
        self.post_interaction_model = LogisticRegression(C = 1/self.re_fit_alpha, penalty = 'l1', max_epochs = 5000, max_iter=100)
        self.post_interaction_model.fit(Chi_post_sparsity, y)
        
        return self
    
   