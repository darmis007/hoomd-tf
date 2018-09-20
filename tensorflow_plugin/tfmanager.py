import tensorflow as tf
import numpy as np
import sys, logging, os, pickle, cProfile, queue, time

def main(q, tasklock, write_tensorboard=False, device='/gpu:0', profile=False):

    tfm_args = q.get()
    tfm = TFManager(q=q, tasklock=tasklock, device=device, write_tensorboard=write_tensorboard, **tfm_args)
    if(profile):
        cProfile.runctx('tfm.start_loop()', globals(), locals(), filename='tf_profile.out')
    else:
        tfm.start_loop()

def load_op_library(op):
    import hoomd.tensorflow_plugin
    path = hoomd.tensorflow_plugin.__path__[0]
    try:
        mod = tf.load_op_library(os.path.join(path, op, 'lib_{}_op.so'.format(op)))
    except IOError:
        raise IOError('Unable to load OP {}'.format(op))
    return mod


class TFManager:
    def __init__(self, graph_info, device,q, tasklock,
                positions_buffer, nlist_buffer,
                forces_buffer, virial_buffer, log_filename,
                dtype, debug, write_tensorboard, use_feed, save_period):

        self.log = logging.getLogger('tensorflow')
        fh = logging.FileHandler(log_filename)
        self.log.addHandler(fh)
        self.log.setLevel(logging.INFO)

        self.device = device
        self.q = q
        self.tasklock = tasklock
        self.positions_buffer = positions_buffer
        self.nlist_buffer = nlist_buffer
        self.forces_buffer = forces_buffer
        self.virial_buffer = virial_buffer
        self.debug = debug
        self.step = 0
        self.graph_info = graph_info
        self.dtype = dtype
        self.write_tensorboard = write_tensorboard
        self.use_feed = use_feed
        self.save_period = save_period

        self.log.info('Starting TF Session Manager. MMAP is at {:x}, {:x}. Dtype is {}'.format(positions_buffer,forces_buffer, dtype))
        self.model_directory = self.graph_info['model_directory']
        self.N = self.graph_info['N']
        self.nneighs = self.graph_info['NN']
        self.out_nodes = []

        with tf.device(self.device):
            self._prepare_graph()
            if graph_info['output_forces']:
                self.log.info('This TF Graph can modify forces.')
                self._prepare_forces()
            else:
                self.log.info('This TF Graph will not modify forces.')

        for n in self.graph_info['out_nodes']:
            self.out_nodes.append(tf.get_default_graph().get_tensor_by_name(n))

    def _update(self, sess, feed_dict=None):

        #pf = tf.get_default_graph().get_tensor_by_name('force-gradient/nlist-pairwise-force-gradient:0')
        #self.out_nodes += [tf.Print(self.forces, [self.forces], summarize=1000)]
        #self.out_nodes += [tf.Print(self.nlist, [self.nlist], summarize=1000)]
        result = sess.run(self.out_nodes, feed_dict=feed_dict)

        if self.step % self.save_period == 0:
            self._save_model(sess, result)
        self.step += 1

        return result

    def _save_model(self, sess, result):
        if result is None:
            return
        if self.saver is not None:
            self.log.info('Writing {} variables at step {}'.format(len(tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)), self.step))
            self.saver.save(sess, os.path.join(self.model_directory, 'model'), global_step=self.step)
        if self.write_tensorboard:
            self.log.info('Writing tensorboard at step {}'.format(self.step))
            #last out_node should be merged summary (set in _attach_tensorboard)
            self.tb_writer.add_summary(result[-1], self.step)

    def _prepare_graph(self):
        ipc_to_tensor_module = load_op_library('ipc2tensor')
        ipc_to_tensor = ipc_to_tensor_module.ipc_to_tensor

        self.log.info('initializing  positions ipc_to_tensor at address {:x} with size {} x 4'.format(self.positions_buffer, self.N))
        self.log.info('initializing nlist ipc_to_tensor at address {:x} with size {} x 4'.format(self.nlist_buffer, self.nneighs * self.N))
        self.positions = ipc_to_tensor(address=self.positions_buffer, shape=[self.N, 4], T=self.dtype, name='positions-input')
        self.nlist = ipc_to_tensor(address=self.nlist_buffer, shape=[self.N, self.nneighs, 4], T=self.dtype, name='nlist-input')
        #now cast if graph dtype are different
        if self.graph_info['dtype'] != self.dtype:
            self.positions = tf.cast(self.positions, self.graph_info['dtype'])
            self.nlist = tf.cast(self.nlist, self.graph_info['dtype'])

        input_map = {self.graph_info['nlist']: self.nlist, self.graph_info['positions'] : self.positions}

        if not self.graph_info['output_forces']:
            #if the graph outputs forces
            self.log.info('initializing nlist ipc_to_tensor at address {:x} with size {} x 4'.format(self.nlist_buffer, self.nneighs * self.N))
            self.forces = ipc_to_tensor(address=self.forces_buffer, shape=[self.N, 4], T=self.dtype, name='forces-input')
            if self.graph_info['dtype'] != self.dtype:
                self.forces = tf.cast(self.forces, self.graph_info['dtype'])
            input_map[self.graph_info['forces']] = self.forces

        #now insert into graph
        try:
            self.graph = tf.train.import_meta_graph(os.path.join(self.model_directory,'model.meta'), input_map=input_map, import_scope='')
        except ValueError:
            raise ValueError('Your graph ({}) must contain the following tensors: forces, nlist, positions'.format(os.path.join(self.model_directory,'model.meta')))

    def _prepare_forces(self):
        #insert the output forces
        try:
            out = tf.get_default_graph().get_tensor_by_name(self.graph_info['forces'])
            #make sure forces will be output in correct precision to hoomd
            self.forces = tf.cast(out, self.dtype)
            if self.graph_info['virial'] is not None:
                out = tf.get_default_graph().get_tensor_by_name(self.graph_info['virial'])
                #make sure forces will be output in correct precision to hoomd
                self.virial = tf.cast(out, self.dtype)
            else:
                self.log.warning('No virial computed in graph. Pressure may be inaccurate!')
        except ValueError:
            raise ValueError('Your graph must contain the following tensors: forces, nlist, positions')
        tensor_to_ipc_module = load_op_library('tensor2ipc')
        tensor_to_ipc = tensor_to_ipc_module.tensor_to_ipc
        self.out_nodes.append(tensor_to_ipc(self.forces, address=self.forces_buffer, maxsize=self.N * 4))
        self.log.info('initializing force tensor_to_ipc: {:x} to {:x}'.format(self.forces_buffer, self.forces_buffer + self.N * 4))
        if self.graph_info['virial'] is not None:
            #virial is Nx3x3
            self.out_nodes.append(tensor_to_ipc(self.virial, address=self.virial_buffer, maxsize=self.N * 9))
            self.log.info('initializing virial tensor_to_ipc: {:x} to {:x}'.format(self.virial_buffer, self.virial_buffer + self.N * 9))

    def _attach_tensorboard(self, sess):

        self.summaries = tf.summary.merge_all()
        self.tb_writer = tf.summary.FileWriter(os.path.join(self.model_directory, 'tensorboard'),
                                      sess.graph)
        tf.global_variables_initializer()
        self.out_nodes += [self.summaries]


    def start_loop(self):

        self.log.info('Constructed TF Model graph')
        #make it grow as memory is needed instead of consuming all
        gpu_options = tf.GPUOptions(allow_growth=True)
        config=tf.ConfigProto(gpu_options=gpu_options)
        with tf.Session(config=config) as sess:
            #resore model checkpoint if there are variables
            if len(tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)) > 0:                             
                #first initialize
                self.log.info('Found trainable variables...')
                sess.run(tf.global_variables_initializer())
                self.log.info('Trainable vars initialized')
                self.saver = tf.train.Saver()
                checkpoint = tf.train.latest_checkpoint(self.model_directory)
                if checkpoint is not None:
                    self.saver.restore(sess, checkpoint)
            else:
                self.saver = None
            if self.debug:
                from tensorflow.python import debug as tf_debug
                sess = tf_debug.TensorBoardDebugWrapperSession(sess, 'localhost:6064')
                self.log.info('You must (first!) attach tensorboard by running '
                            'tensorboard --logdir {} --debugger_port 6064'
                            .format(os.path.join(self.model_directory, 'tensorboard')))
            if self.write_tensorboard:
                self._attach_tensorboard(sess)
            #indicating we are ready to begin
            self.q.task_done()
            cumtime = 0
            result = None

            if self.use_feed:
                feed_dict = None
                while True:
                    try:
                        feed_name_dict = self.q.get()
                    except queue.empty:
                        self.log.info('Received exit. Leaving TF Update Loop. \n TF Update time (excluding communication) is {}'.format(cumtime))
                        self._save_model(sess, result)
                        break
                    #convert name keys to actual tensor keys
                    try:
                        feed_dict = dict()
                        for k,v in feed_name_dict.items():
                            tensor = tf.get_default_graph().get_tensor_by_name(k)
                            feed_dict[tensor] = v
                        last_clock = time.perf_counter()
                        result = self._update(sess, feed_dict=feed_dict)
                    finally:
                        cumtime += (time.perf_counter() - last_clock)
                        self.q.task_done()
            else:
                while True:
                    if not self.tasklock.start():
                        self.log.info('Received exit. Leaving TF Update Loop. \n TF Update time (excluding communication) is {}'.format(cumtime))
                        self._save_model(sess, result)
                        break
                    last_clock = time.perf_counter()
                    result = self._update(sess)
                    cumtime += (time.perf_counter() - last_clock)
                    self.tasklock.end()







