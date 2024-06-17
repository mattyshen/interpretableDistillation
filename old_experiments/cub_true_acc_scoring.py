import pandas as pd
import numpy as np
import sys

sys.path.append('..')

from interpretDistill.fourierDistill import *
from interpretDistill.binaryTransformer import *

def process_csv(df):
    y_true = df['y_true']
    y_hat = df['y_hat']
    X = df.drop(columns = ['id', 'y_true', 'y_hat'])
    return X, y_true, y_hat

def scoring_df_maker(model_list, model_names, Xy, y_hats, train_time):
    df = pd.DataFrame(columns = ['Model', 'Train Acc', 'Val Acc', 'Test Acc'])
    df['Model'] = model_names
    
    for xy, j in zip(Xy, df.columns[1:]):
        df[j] = [np.mean(m.predict(xy[0]) == xy[1]) for m in model_list]
        
    df['Train Time'] = train_time

    #[ftd_bo_train, ftd_bb_train, ftd_bo_val, ftd_bb_val, ftd_bo_tv, ftd_bb_tv]
    df['Total Num Features'] = [m.regression_model.coef_.shape[1] for m in model_list]
    df['Avg Num Selected Features'] = [np.mean(np.sum(m.regression_model.coef_ != 0, axis = 1)) for m in model_list]
    
    df.loc[len(df)] = ['ResNet18 CUB']+[np.mean(y_hat == y) for (_, y), y_hat in zip(Xy, y_hats)]+[-1, -1, -1]
    
    return df

Xy_concept_train = pd.read_csv('data/Xy_concept_train.csv', index_col = [0])
Xy_concept_val = pd.read_csv('data/Xy_concept_val.csv', index_col = [0])
Xy_concept_test = pd.read_csv('data/Xy_concept_test.csv', index_col = [0])
X_concept_train, y_concept_train_true, y_concept_train_hat = process_csv(Xy_concept_train)
X_concept_val, y_concept_val_true, y_concept_val_hat = process_csv(Xy_concept_val)
X_concept_test, y_concept_test_true, y_concept_test_hat = process_csv(Xy_concept_test)

ftd_bo_train = FTDistillClassifierCV(size_interactions=2, k_cv = 3)
ftd_bo_val = FTDistillClassifierCV(size_interactions=2, k_cv = 3)
ftd_bo_tv = FTDistillClassifierCV(size_interactions=2, k_cv = 3)

train_time = []

print('begin fitting')
start = time.time()
ftd_bo_train.fit(X_concept_train, y_concept_train_true)
end = time.time()
train_time.append(end-start)
print('bo_train concluded')
start = time.time()
ftd_bo_val.fit(X_concept_val, y_concept_val_true)
end = time.time()
train_time.append(end-start)
print('bo_val concluded')
start = time.time()
ftd_bo_tv.fit(pd.concat([X_concept_train, X_concept_val], axis = 0), pd.concat([y_concept_train_true, y_concept_val_true], axis = 0))
end = time.time()
train_time.append(end-start)
print('bo_tv concluded')

ftd_list = [ftd_bo_train, ftd_bo_val, ftd_bo_tv]
ftd_names = ['(concept, true, train)', '(concept, true, val)','(concept, true, tv)']

Xy_true = [(X_concept_train, y_concept_train_true), (X_concept_val, y_concept_val_true), (X_concept_test, y_concept_test_true)]
#Xy_hat = [(X_concept_train, y_concept_train_hat), (X_concept_val, y_concept_val_hat), (X_concept_test, y_concept_test_hat)]
y_hats = [y_concept_train_hat, y_concept_val_hat, y_concept_test_hat]

df_true = scoring_df_maker(ftd_list, ftd_names, Xy_true, y_hats, train_time)
#df_hat = scoring_df_maker(ftd_list, ftd_names, Xy_hat, y_truth)

df_true.to_csv('CUB_concept_acc_true_noresnet.csv')
#df_hat.to_csv('CUB_concept_acc_hat.csv')