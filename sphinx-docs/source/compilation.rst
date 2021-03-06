.. _compiling:

Compiling
=========

Prerequisites
----------------

The following packages are required to compile:

::

    tensorflow < 2.0
    hoomd-blue >= 2.5.2
    numpy
    tbb-devel (only for hoomd-blue 2.8 and above)

tbb-devel is required for hoomd-blue 2.8 or above when using the
hoomd-blue conda release. It is not automatically installed when
installing hoomd-blue, so use ``conda install -c conda-forge
tbb-devel`` to install. The Tensorflow version should be any
Tensorflow 1 release. The higher versions, like 1.14, 1.15, will give
lots of warnings about migrating code to Tensorflow 2.0. It is
recommended you install via pip:

.. code:: bash

  pip install tensorflow-gpu==1.15.0

Python and GCC requirements
----------------

If you install tensorflow with pip, as recommended, this
provides a pre-built version of tensorflow which has
specific GCC and Python versions. When you compile
hoomd-tf, these must match what is found by cmake. So if your version
of tensorflow used gcc-7x, then you must have gcc-7x available on your machine.
The cmake script in hoomd-tf will check for this and tell you if they do not match.


.. _simple_compiling:

Simple Compiling
----------------

Install hoomd-blue and Tensorflow by your preferred method. If you
want to install hoomd-blue without GPU support, you can just use the
conda release via ``conda install -c conda-forge hoomd==2.5.2``. You
should then similarly use the CPU version of Tensorflow (``pip install tensorflow==1.15``). If you would
like GPU support, compile hoomd-blue using `their instructions
<http://hoomd-blue.readthedocs.io>`_. Remember that pip is recommended
for installing Tensorflow. Here are steps **after** installing
hoomd-blue and tensorflow

.. code:: bash

    git clone https://github.com/ur-whitelab/hoomd-tf
    cd hoomd-tf && mkdir build && cd build
    CXX=g++ CC=gcc cmake ..
    make install

That's it! Check your install by running ``python
htf/test-py/test_sanity.py``.  If you have installed with GPU support, also
check with ``python htf/test-py/_test_gpu_sanity.py``.

.. _compiling_with_hoomd_blue:

Compiling with Hoomd-Blue
-------------------------

Use this method if you need to compile with developer flags on or other
special requirements.

.. code:: bash

    git clone --recursive https://bitbucket.org/glotzer/hoomd-blue hoomd-blue

We typically use v2.5.2 of hoomd-blue

.. code:: bash

    cd hoomd-blue && git checkout tags/v2.5.2

Now we put our plugin in the source directory with a softlink:

.. code:: bash

    git clone https://github.com/ur-whitelab/hoomd-tf
    ln -s $HOME/hoomd-tf/htf $HOME/hoomd-blue/hoomd

Now compile (from hoomd-blue directory). Modify options for speed if
necessary. Set build type to `DEBUG` if you need to troubleshoot.

.. code:: bash

    mkdir build && cd build
    CXX=g++ CC=gcc cmake .. -DCMAKE_BUILD_TYPE=Release \
     -DENABLE_CUDA=ON -DENABLE_MPI=OFF\
     -DBUILD_HPMC=off -DBUILD_CGCMM=off -DBUILD_MD=on\
     -DBUILD_METAL=off -DBUILD_TESTING=off -DBUILD_DEPRECATED=off -DBUILD_MPCD=OFF \
     -DCMAKE_INSTALL_PREFIX=`python -c "import site; print(site.getsitepackages()[0])"`

Now compile with make:

.. code:: bash

    make

Option 1: Put build directory on your python path:

.. code:: bash

    export PYTHONPATH="$PYTHONPATH:`pwd`"

Option 2: Install in your python site-packages

.. code:: bash

    make install

.. _conda_environments:

Conda Environments
------------------

If you are using a conda environment, you may need to force cmake to
find your python environment. This is rare, we only see it on our
compute cluster which has multiple conflicting version of python and
conda. The following additional flags can help with this:

.. code:: bash

    export CMAKE_PREFIX_PATH=/path/to/environment
    CXX=g++ CC=gcc cmake .. \
    -DPYTHON_INCLUDE_DIR=$(python -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())") \
    -DPYTHON_LIBRARY=$(python -c "import distutils.sysconfig as sysconfig; print(sysconfig.get_config_var('LIBDIR'))") \
    -DPYTHON_EXECUTABLE=$(which python) \
    -DCMAKE_BUILD_TYPE=Release -DENABLE_CUDA=ON -DENABLE_MPI=OFF -DBUILD_HPMC=off -DBUILD_CGCMM=off -DBUILD_MD=on \
    -DBUILD_METAL=off -DBUILD_TESTING=off -DBUILD_DEPRECATED=off -DBUILD_MPCD=OFF \
    -DCMAKE_INSTALL_PREFIX=`python -c "import site; print(site.getsitepackages()[0])"`

.. _updating_compiled_code:

Updating Compiled Code
----------------------

If you are developing frequently, add the build directory to your
python path instead of `make install` (only works with hoomd-blue
compiled). Then if you modify C++ code, only run make (not cmake). If
you modify python, just copy over py files (``htf/*py`` to
``build/hoomd/htf``).

.. _mbuild_environment:

MBuild Environment
------------------

If you are using mbuild, please follow these additional install steps:

.. code:: bash

    conda install numpy cython
    pip install requests networkx matplotlib scipy pandas plyplus lxml mdtraj oset
    conda install -c omnia -y openmm parmed
    conda install -c conda-forge --no-deps -y packmol gsd
    pip install --upgrade git+https://github.com/mosdef-hub/foyer git+https://github.com/mosdef-hub/mbuild

.. _hpc_installation:

HPC Installation
=====================

These are instructions for our group's cluster (BlueHive), and not for general users. **Feeling Lucky?** Try this for quick results

.. code:: bash

    module load cmake gcc/7.3.0 cudnn/10.0-7.5.0 anaconda3/2019.10
    export PYTHONNOUSERSITE=True
    conda create -n hoomd-tf python=3.7
    source activate hoomd-tf
    export CMAKE_PREFIX_PATH=/path/to/environment
    python -m pip install tensorflow-gpu==1.15.0
    conda install -c conda-forge hoomd==2.5.2
    git clone https://github.com/ur-whitelab/hoomd-tf
    cd hoomd-tf && mkdir build && cd build
    CXX=g++ CC=gcc cmake .. \
      -DPYTHON_INCLUDE_DIR=$(python -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())") \
      -DPYTHON_LIBRARY=$(python -c "import distutils.sysconfig as sysconfig; print(sysconfig.get_config_var('LIBDIR'))") \
      -DPYTHON_EXECUTABLE=$(which python)
    make install
    cd .. && python htf/test-py/test_sanity.py

Here are the more detailed steps. Clone the ``hoomd-tf`` repo
and then follow these steps:

Load the modules necessary:

.. code:: bash

    module load cmake gcc/7.3.0 cudnn/10.0-7.5.0 anaconda3/2019.10

Set-up virtual python environment *ONCE* to keep packages isolated.

.. code:: bash

    conda create -n hoomd-tf python=3.7
    source activate hoomd-tf
    python -m pip install tensorflow-gpu==1.15.0

Then whenever you login and *have loaded modules*:

.. code:: bash

    source activate hoomd-tf


Continue following the compling steps below to complete install.
The simple approach is recommended but **use the following
different cmake step**

.. code:: bash

  export CMAKE_PREFIX_PATH=/path/to/environment
  CXX=g++ CC=gcc cmake ..

If using the hoomd-blue compilation, **use the following
different cmake step**

.. code:: bash

    export CMAKE_PREFIX_PATH=/path/to/environment
    CXX=g++ CC=gcc cmake .. \
    -DPYTHON_INCLUDE_DIR=$(python -c "from distutils.sysconfig import get_python_inc; print(get_python_inc())") \
    -DPYTHON_LIBRARY=$(python -c "import distutils.sysconfig as sysconfig; print(sysconfig.get_config_var('LIBDIR'))") \
    -DPYTHON_EXECUTABLE=$(which python) \
    -DCMAKE_BUILD_TYPE=Release -DENABLE_CUDA=ON -DENABLE_MPI=OFF -DBUILD_HPMC=off -DBUILD_CGCMM=off -DBUILD_MD=on \
    -DBUILD_METAL=off -DBUILD_TESTING=off -DBUILD_DEPRECATED=off -DBUILD_MPCD=OFF \
    -DCMAKE_INSTALL_PREFIX=`python -c "import site; print(site.getsitepackages()[0])"`\
    -DNVCC_FLAGS="-ccbin /software/gcc/7.3.0/bin"

.. _optional_dependencies:

Optional Dependencies
=====================
Following packages are optional:
.. code:: bash

   MDAnalysis 
 
 :py:class:`utils.run_from_trajectory` uses `MDAnalysis` for trajectory parsing
