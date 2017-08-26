import numpy as np
import tensorflow as tf
import math


## Just used to get sparse representation of input data
def dense_array_to_sparse(x, expand_dims=False):
    if expand_dims: 
        x = np.expand_dims(x, 2)
    inds = np.array(list(zip(*x.nonzero())))
    vals = x[x.nonzero()]
    shape = x.shape
    return {'indices':inds, 'values':vals, 'dense_shape':shape}

## Mostly used for debugging 
def sparse_array_to_dense(x_sp, shape=None):
    if shape is None:
        shape = x_sp['dense_shape']    
    out = np.zeros(shape)
    inds = list(zip(*x_sp['indices']))
    out[inds] = x_sp['values']
    return out


def dense_tensor_to_sparse(x, shape=None):
    if shape is None:
        shape = x.shape
    inds = tf.where(tf.not_equal(x, 0))
    vals = tf.gather_nd(x, inds)    
    return tf.SparseTensorValue(inds, vals, shape)


def sparse_tensor_to_dense(x_sp, shape=None):
    if shape is None:
        shape = x_sp.dense_shape
    return tf.scatter_nd(x_sp.indices, x_sp.values, x_sp.dense_shape)
    # return tf.sparse_tensor_to_dense(x_sp)


## This function works, but it calls sparse_tensor_to_dense, which could be inefficient 
def sparse_tensor_mask_to_sparse(x_sp, mask_sp, shape=None, name=None):
    if shape is None:
        shape = x_sp.dense_shape
    K = shape[2]
    num_vals = tf.shape(mask_sp.indices)[0]
    inds_exp = tf.reshape(tf.range(K, dtype=tf.int64), [-1, 1])
    inds_exp = tf.reshape(tf.tile(inds_exp, tf.stack([1, num_vals])), [-1,1])

    x = sparse_tensor_to_dense(x_sp, shape=shape)

    inds = tf.slice(mask_sp.indices, begin=[0,0], size=[-1,2])

    inds = tf.tile(inds, multiples=[K,1])
    inds = tf.concat((inds, inds_exp), axis=1)
    vals = tf.reshape(tf.gather_nd(x, inds), [-1])    

    return tf.SparseTensorValue(inds, vals, shape)


# def sparse_tensor_mask_to_sparse(x_sp, mask_sp, shape=None, name=None):
#     if shape is None:
#         shape = x_sp.dense_shape
#     K = shape[2]
#     num_vals = tf.shape(mask_sp.indices)[0]

#     inds_exp = tf.reshape(tf.tile(tf.range(K, dtype=tf.int64), multiples=tf.stack([num_vals])), [-1,1])
#     inds = tf.slice(mask_sp.indices, begin=[0,0], size=[-1,2])    
#     inds = tf.reshape(tf.tile(inds, [1,K]), [-1,2])
#     inds = tf.concat((inds, inds_exp), axis=1)

#     select = tf.cast(tf.equal(x_sp.indices, tf.expand_dims(inds, axis=1)), dtype=tf.int32)
#     # select = tf.cast(tf.reduce_sum(tf.reduce_prod(select, axis=2), axis=0), dtype=tf.bool)
#     # vals = tf.boolean_mask(x_sp.values, select) ## Causes memory problems because tf converts indexed slices to a dense tensor
#     select = tf.reduce_sum(tf.reduce_prod(select, axis=2), axis=0)
#     vals = tf.dynamic_partition(x_sp.values, partitions=select, num_partitions=2)[1]

#     return tf.SparseTensorValue(inds, vals, shape)


# ## This version doesn't call sparse_tensor_to_dense(), but it eats a large amout of memory. I am not sure why  
# def sparse_tensor_mask_to_sparse(x_sp, mask_sp, shape=None, name=None):
#     if shape is None:
#         shape = x_sp.dense_shape
#     K = shape[2]    
#     num_vals = tf.shape(mask_sp.indices)[0]

#     inds_exp = tf.reshape(tf.tile(tf.range(K, dtype=tf.int64), multiples=tf.stack([num_vals])), [-1,1])
#     inds = tf.slice(mask_sp.indices, begin=[0,0], size=[-1,2])    
#     inds = tf.reshape(tf.tile(inds, [1,K]), [-1,2])
#     inds = tf.concat((inds, inds_exp), axis=1)

#     select = tf.cast(tf.equal(x_sp.indices, tf.expand_dims(inds, axis=1)), dtype=tf.float32)
#     select = tf.reduce_sum(tf.reduce_prod(select, axis=2), axis=0)

#     vals = x_sp.values * select
#     vals = tf.gather_nd(vals, tf.where(tf.not_equal(vals, 0)))
    
#     return tf.SparseTensorValue(inds, vals, shape)
    

def sparse_apply_activation(x_sp, activation):
    return tf.SparseTensorValue(x_sp.indices, activation(x_sp.values), x_sp.dense_shape)


## Like tf.tensordot, where first input is sparse 
def sparse_tensordot(tensor_sp, param, in_shape, out_shape):
    output = tf.reshape(tf.sparse_tensor_dense_matmul(tf.sparse_reshape(tensor_sp, in_shape), param), out_shape)
    return output


## Like tf.tensordot but with sparse inputs and outputs. Output has non-zero value only where input has non-zero value 
def sparse_tensordot_sparse(tensor_sp, param, in_shape, units):
    N,M,K = in_shape
    num_vals = tf.shape(tensor_sp.indices)[0]
    num_unique = tf.cast(tf.divide(num_vals, K), dtype=tf.int32)
    
    ## use numpy? 
    inds_exp = tf.reshape(tf.tile(tf.range(units, dtype=tf.int64), multiples=tf.stack([num_unique])), [-1,1])
    inds = tf.strided_slice(tensor_sp.indices, begin=[0,0], end=[num_vals, 2], strides=[K,1])
    inds = tf.reshape(tf.tile(inds, [1,units]), [-1,2])
    inds = tf.concat((inds, inds_exp), axis=1)

    vals = tf.matmul(tf.reshape(tensor_sp.values, shape=[-1,K]), param)
    vals = tf.reshape(vals, shape=[-1])

    return tf.SparseTensorValue(inds, vals, [N,M,units])


## Eating huge amounts of memory 
def sparse_dropout(x_sp, rate=0.0, training=False, shape=None):    
    if not training:
        return x_sp
    if shape is None:
        shape = x_sp.dense_shape
    N = shape[0]
    M = shape[1]

    n_inds = tf.expand_dims(np.random.choice(range(N), size=math.floor(N*rate), replace=False), axis=1) ## Rows to drop out 
    n_mask = tf.cast(tf.not_equal(x_sp.indices[:,0], n_inds), dtype=tf.int32)
    n_mask = tf.reduce_prod(n_mask, axis=0)

    vals = tf.dynamic_partition(x_sp.values, n_mask, num_partitions=2)[1] ## I think this function is eating large amounts of memory 
    inds = tf.dynamic_partition(x_sp.indices, n_mask, num_partitions=2)[1]

    m_inds = tf.expand_dims(np.random.choice(range(M), size=math.floor(M*rate), replace=False), axis=1) ## Columns to drop out 
    m_mask = tf.cast(tf.not_equal(inds[:,1], m_inds), dtype=tf.int32)
    m_mask = tf.reduce_prod(m_mask, axis=0)

    vals = tf.dynamic_partition(vals, m_mask, num_partitions=2)[1] 
    inds = tf.dynamic_partition(inds, m_mask, num_partitions=2)[1]

    vals = vals * (1./rate)**2  ## scale entries to maintain total sum (matching tf.layers.dropout)

    return tf.SparseTensorValue(inds, vals, shape)


## x_sp is a sparse tensor of shape [N,M,K], y is dense of shape [1,M,K], [N,1,K], or [1,1,K].
## Broadcast add y onto the sparse coordinates of x_sp.
## Produces a sparse tensor with the same shape as x_sp, and non-zero values corresponding to those of x_sp
def sparse_tensor_broadcast_dense_add(x_sp, y, broadcast_axis=None, shape=None):
    if shape is None:
        shape = x_sp.dense_shape
    K = shape[2]    
    num_vals = tf.shape(x_sp.indices)[0]

    if broadcast_axis is 0:
        temp_inds = tf.strided_slice(x_sp.indices, begin=[0,0], end=[num_vals,2], strides=[K,1])
        temp_inds = tf.slice(temp_inds, begin=[0,1], size=[-1,1])
        new_vals = tf.cast(tf.gather_nd(tf.reshape(y, shape=[-1,K]), temp_inds), tf.float32)
        vals = tf.reshape(x_sp.values, shape=[-1,K]) + new_vals
        # vals = tf.reshape(vals, shape=[num_vals])
        vals = tf.reshape(vals, shape=[-1])
        return tf.SparseTensorValue(x_sp.indices, vals, shape)

    elif broadcast_axis is 1:
        temp_inds = tf.strided_slice(x_sp.indices, begin=[0,0], end=[num_vals,2], strides=[K,1])
        temp_inds = tf.slice(temp_inds, begin=[0,0], size=[-1,1])
        new_vals = tf.cast(tf.gather_nd(tf.reshape(y, shape=[-1,K]), temp_inds), tf.float32)
        vals = tf.reshape(x_sp.values, shape=[-1,K]) + new_vals
        # vals = tf.reshape(vals, shape=[num_vals])
        vals = tf.reshape(vals, shape=[-1])
        return tf.SparseTensorValue(x_sp.indices, vals, shape)

    else:
        vals = tf.reshape(x_sp.values, shape=[-1,K])
        vals = tf.reshape(tf.add(vals, y), shape=[-1])
        return tf.SparseTensorValue(x_sp.indices, vals, shape)


## This one seems to be working well. It produces a dense tensor 
def sparse_reduce(x_sp, mode='sum', axis=None, shape=None, zero_threshold=0.00001):
    if shape is None:
        shape = x_sp.dense_shape
    N = shape[0]
    M = shape[1]
    K = shape[2]

    if 'sum' in mode:
        op = tf.unsorted_segment_sum
    elif 'max' in mode:
        op = tf.unsorted_segment_max
    elif 'mean' in mode:
        if axis is 0: # Matches tf.reduce_mean, but maybe not dense implementation (divide by num non-zeros?)
            d = N
        elif axis is 1:
            d = M
        else:
            d = N*M
        op = lambda *args, **kwargs: tf.unsorted_segment_sum(*args, **kwargs) / d
    else:
        print('\n--> unknown mode in sparse_reduce\n')
        return 

    if axis is 0:
        inds_1 = tf.squeeze(tf.slice(x_sp.indices, [0,1], [-1,1]))
        inds_2 = tf.squeeze(tf.slice(x_sp.indices, [0,2], [-1,1]))
        inds = K * inds_1 + inds_2
        vals = op(x_sp.values, inds, num_segments=M*K)
        vals = tf.where(tf.greater(vals, zero_threshold), vals, tf.zeros_like(vals)) ## Rounding, to avoid numerical representation issues
        return tf.reshape(vals, [1,M,K])
    elif axis is 1:
        inds_0 = tf.squeeze(tf.slice(x_sp.indices, [0,0], [-1,1]))
        inds_2 = tf.squeeze(tf.slice(x_sp.indices, [0,2], [-1,1]))
        inds = K * inds_0 + inds_2
        vals = op(x_sp.values, inds, num_segments=N*K)
        vals = tf.where(tf.greater(vals, zero_threshold), vals, tf.zeros_like(vals)) ## Rounding, to avoid numerical representation issues
        return tf.reshape(vals, [N,1,K])
    else:
        inds = tf.squeeze(tf.slice(x_sp.indices, [0,2], [-1,1]))
        vals = op(x_sp.values, inds, num_segments=K)
        vals = tf.where(tf.greater(vals, zero_threshold), vals, tf.zeros_like(vals)) ## Rounding, to avoid numerical representation issues
        return tf.reshape(vals, [1,1,K])





