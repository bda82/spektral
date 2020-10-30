"""
This example shows how to perform regression of molecular properties with the
QM9 database, using a simple GNN in disjoint mode.
"""

import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from tensorflow.keras.layers import Input, Dense
from tensorflow.keras.losses import MeanSquaredError
from tensorflow.keras.models import Model
from tensorflow.keras.optimizers import Adam

from spektral.data import DisjointLoader
from spektral.datasets import qm9
from spektral.datasets.qm9 import QM9
from spektral.layers import EdgeConditionedConv, ops, GlobalSumPool
from spektral.data.utils import to_disjoint, batch_generator
from spektral.utils import label_to_one_hot

################################################################################
# PARAMETERS
################################################################################
learning_rate = 1e-3  # Learning rate
epochs = 10           # Number of training epochs
batch_size = 32       # Batch size

################################################################################
# LOAD DATA
################################################################################
dataset = QM9(amount=1000)  # Set amount=None to train on whole dataset

# Parameters
F = dataset.F          # Dimension of node features
S = dataset.S          # Dimension of edge features
n_out = dataset.n_out  # Dimension of the target

# Train/test split
idxs = np.random.permutation(len(dataset))
split = int(0.9 * len(dataset))
dataset_tr, dataset_te = dataset[:split], dataset[split:]

################################################################################
# BUILD MODEL
################################################################################
X_in = Input(shape=(F,), name='X_in')
A_in = Input(shape=(None,), sparse=True, name='A_in')
E_in = Input(shape=(S,), name='E_in')
I_in = Input(shape=(), name='segment_ids_in', dtype=tf.int32)

X_1 = EdgeConditionedConv(32, activation='relu')([X_in, A_in, E_in])
X_2 = EdgeConditionedConv(32, activation='relu')([X_1, A_in, E_in])
X_3 = GlobalSumPool()([X_2, I_in])
output = Dense(n_out)(X_3)

# Build model
model = Model(inputs=[X_in, A_in, E_in, I_in], outputs=output)
opt = Adam(lr=learning_rate)
loss_fn = MeanSquaredError()


@tf.function(
    input_signature=((tf.TensorSpec((None, F), dtype=tf.float64),
                      tf.SparseTensorSpec((None, None), dtype=tf.int64),
                      tf.TensorSpec((None, S), dtype=tf.float64),
                      tf.TensorSpec((None,), dtype=tf.int64)),
                     tf.TensorSpec((None, n_out), dtype=tf.float64)),
    experimental_relax_shapes=True)
def train_step(inputs, target):
    with tf.GradientTape() as tape:
        predictions = model(inputs, training=True)
        loss = loss_fn(target, predictions)
        loss += sum(model.losses)
    gradients = tape.gradient(loss, model.trainable_variables)
    opt.apply_gradients(zip(gradients, model.trainable_variables))
    return loss


################################################################################
# FIT MODEL
################################################################################
current_batch = 0
model_loss = 0

print('Fitting model')
loader_tr = DisjointLoader(dataset_tr, batch_size=batch_size, epochs=epochs, shuffle=True)
for batch in loader_tr:
    outs = train_step(*batch)

    model_loss += outs
    current_batch += 1
    if current_batch == loader_tr.steps_per_epoch:
        print('Loss: {}'.format(model_loss / loader_tr.steps_per_epoch))
        model_loss = 0
        current_batch = 0

################################################################################
# EVALUATE MODEL
################################################################################
print('Testing model')
model_loss = 0
loader_te = DisjointLoader(dataset_te, batch_size=batch_size)
for batch in loader_te:
    inputs, target = batch
    predictions = model(inputs, training=False)
    model_loss += loss_fn(target, predictions)
model_loss /= loader_te.steps_per_epoch
print('Done. Test loss: {}'.format(model_loss))
