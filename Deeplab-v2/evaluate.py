"""Evaluation script for the DeepLab-ResNet network on the validation subset
   of PASCAL VOC dataset.

This script evaluates the model on 1449 validation images.
"""

from __future__ import print_function

import argparse
from datetime import datetime
import os
import sys
import time

import tensorflow as tf
import numpy as np

from model.network import ResNet_segmentation
from utils import ImageReader, prepare_label

IMG_MEAN = np.array((104.00698793,116.66876762,122.67891434), dtype=np.float32)

DATA_DIRECTORY = '/data_b/bd-recommend/zhenyutang/logs/VOCdevkit/VOC2012'
DATA_LIST_PATH = './dataset_voc2012/val.txt'
IGNORE_LABEL = 255
NUM_CLASSES = 21
NUM_STEPS = 1449 # Number of images in the validation set.
RESTORE_FROM = './model/model.ckpt-19000'

def get_arguments():
    """Parse all the arguments provided from the CLI.
    
    Returns:
      A list of parsed arguments.
    """
    parser = argparse.ArgumentParser(description="DeepLabLFOV Network")
    parser.add_argument("--data-dir", type=str, default=DATA_DIRECTORY,
                        help="Path to the directory containing the PASCAL VOC dataset.")
    parser.add_argument("--data-list", type=str, default=DATA_LIST_PATH,
                        help="Path to the file listing the images in the dataset.")
    parser.add_argument("--ignore-label", type=int, default=IGNORE_LABEL,
                        help="The index of the label to ignore during the training.")
    parser.add_argument("--num-classes", type=int, default=NUM_CLASSES,
                        help="Number of classes to predict (including background).")
    parser.add_argument("--num-steps", type=int, default=NUM_STEPS,
                        help="Number of images in the validation set.")
    parser.add_argument("--restore-from", type=str, default=RESTORE_FROM,
                        help="Where restore model parameters from.")
    parser.add_argument("--encoder-name", type=str, default='res50',
                        help='name of pre-trained model, res101, res50')

    return parser.parse_args()

def load(saver, sess, ckpt_path):
    '''Load trained weights.
    
    Args:
      saver: TensorFlow saver object.
      sess: TensorFlow session.
      ckpt_path: path to checkpoint file with parameters.
    ''' 
    saver.restore(sess, ckpt_path)
    print("Restored model parameters from {}".format(ckpt_path))

def main():
    """Create the model and start the evaluation process."""
    args = get_arguments()
    
    # Create queue coordinator.
    coord = tf.train.Coordinator()
    
    # Load reader.
    with tf.name_scope("create_inputs"):
        reader = ImageReader(
            args.data_dir,
            args.data_list,
            None, # No defined input size.
            False, # No random scale.
            False, # No random mirror.
            args.ignore_label,
            IMG_MEAN,
            coord)
        image, label = reader.image, reader.label
    image_batch, label_batch = tf.expand_dims(image, dim=0), tf.expand_dims(label, dim=0) # Add one batch dimension.

    # Create network.
    if args.encoder_name not in ['res101', 'res50']:
       print('encoder_name ERROR!')
       print("Please input: res101, res50")
       sys.exit(-1)
    else:
       net = ResNet_segmentation(image_batch, args.num_classes, False, args.encoder_name)

    # predictions
    raw_output = net.outputs
    raw_output = tf.image.resize_bilinear(raw_output, tf.shape(image_batch)[1:3,])
    raw_output = tf.argmax(raw_output, axis=3)
    pred = tf.expand_dims(raw_output, dim=3)
    pred = tf.reshape(pred, [-1,])
    # labels
    gt = tf.reshape(label_batch, [-1,])
    # Ignoring all labels greater than or equal to n_classes.
    temp = tf.less_equal(gt, args.num_classes - 1)
    weights = tf.cast(temp, tf.int32)

    # fix for tf 1.3.0
    gt = tf.where(temp, gt, tf.cast(temp, tf.uint8))

    # Which variables to load.
    restore_var = tf.global_variables()
    
    # Predictions.
    raw_output = net.outputs
    raw_output = tf.image.resize_bilinear(raw_output, tf.shape(image_batch)[1:3,])
    raw_output = tf.argmax(raw_output, dimension=3)
    pred = tf.expand_dims(raw_output, dim=3) # Create 4-d tensor.
    pred = tf.reshape(pred, [-1,])

    #groud truth
    gt = tf.reshape(label_batch, [-1,])
    indexes = tf.less_equal(gt, args.num_classes - 1)
    gt = tf.where(indexes, gt, tf.cast(temp, tf.uint8))
    weights = tf.cast(indexes, tf.int32) # Ignoring all labels greater than or equal to n_classes.
    # mIoU
    mIoU, update_op = tf.contrib.metrics.streaming_mean_iou(pred, gt, num_classes=args.num_classes, weights=weights)

    # Pixel accuracy
    accu, accu_update_op = tf.contrib.metrics.streaming_accuracy(
                pred, gt, weights=weights)
    
    # Set up tf session and initialize variables. 
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    sess = tf.Session(config=config)
    init = tf.global_variables_initializer()
    
    sess.run(init)
    sess.run(tf.local_variables_initializer())
    
    # Load weights.
    loader = tf.train.Saver(var_list=restore_var)
    if args.restore_from is not None:
        load(loader, sess, args.restore_from)
    
    # Start queue threads.
    threads = tf.train.start_queue_runners(coord=coord, sess=sess)
    
    # Iterate over training steps.
    for step in range(args.num_steps):
        preds, _, _ = sess.run([pred, update_op, accu_update_op])
        if step % 100 == 0:
            print('step {:d}'.format(step))
    print('Mean IoU: {:.3f}'.format(mIoU.eval(session=sess)))
    print('Pixel Accuracy: {:.3f}'.format(accu.eval(session=sess)))
    coord.request_stop()
    coord.join(threads)
    
if __name__ == '__main__':
    main()
