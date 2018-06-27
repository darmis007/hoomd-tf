// Copyright (c) 2009-2017 The Regents of the University of Michigan
// This file is part of the HOOMD-blue project, released under the BSD 3-Clause License.

#include "TensorflowUpdater.h"
#ifdef ENABLE_CUDA
#include "TensorflowUpdater.cuh"
#endif

#include <iostream>
#include <string.h>
#include <sys/mman.h>

/*! \file TensorflowUpdater.cc
    \brief Definition of TensorflowUpdater
*/

// ********************************
// here follows the code for TensorflowUpdater on the CPU

/*! \param sysdef System to zero the velocities of
*/
TensorflowUpdater::TensorflowUpdater(std::shared_ptr<SystemDefinition> sysdef,
    pybind11::object& py_self,
    unsigned int nneighs)
        : ForceCompute(sysdef),
          _py_self(py_self),
          _input_buffer(NULL),
          _output_buffer(NULL),
          _nneighs(nneighs)
{
    reallocate();
    // connect to the ParticleData to receive notifications when the maximum number of particles changes
     m_pdata->getMaxParticleNumberChangeSignal().connect<TensorflowUpdater, &TensorflowUpdater::reallocate>(this);

}

void TensorflowUpdater::reallocate() {
     // might need to do something so GPU code doesn't call this
    auto m_exec_conf = m_sysdef->getParticleData()->getExecConf();
    // create input/output mmap buffer
    assert(m_pdata);
    _buffer_size = m_pdata->getN();
    //check if allocated
    if(_input_buffer)
        munmap(_input_buffer, _buffer_size*sizeof(Scalar4));
    if(_output_buffer)
        munmap(_output_buffer, _buffer_size*sizeof(Scalar4));
    _input_buffer = static_cast<Scalar4*> (mmap(NULL, _buffer_size*sizeof(Scalar4), PROT_READ|PROT_WRITE, MAP_SHARED|MAP_ANONYMOUS, -1, 0));
    _output_buffer = static_cast<Scalar4*> (mmap(NULL, _buffer_size*sizeof(Scalar4), PROT_READ|PROT_WRITE, MAP_SHARED|MAP_ANONYMOUS, -1, 0));
    if(_input_buffer == MAP_FAILED || _output_buffer == MAP_FAILED) {
        perror("Failed to create mmap");
        m_exec_conf->msg->error() << "Failed to create mmap" << std::endl;
    }
    m_exec_conf->msg->notice(2) << "Created mmaped pages for tensorflow updater (" << _buffer_size*sizeof(Scalar4) / 1024.0 << " kB)" << std::endl;
    m_exec_conf->msg->notice(2) << "At addresses " << _input_buffer << "," << _output_buffer << std::endl;

    _py_self.attr("restart_tf")();
}

TensorflowUpdater::~TensorflowUpdater() {
    // unmap our mmapings
    munmap(_input_buffer, _buffer_size*sizeof(Scalar4));
    munmap(_output_buffer, _buffer_size*sizeof(Scalar4));
    _input_buffer = NULL;
    _output_buffer = NULL;
}

/*! Perform the needed calculations to zero the system's velocity
    \param timestep Current time step of the simulation
*/
void TensorflowUpdater::computeForces(unsigned int timestep)
{
    if (m_prof) m_prof->push("TensorflowUpdater");

    _py_self.attr("start_update")();

    //nneighs == 0 -> send positions instead
    if(_nneighs > 0)
        sendNeighbors();
    else
        sendPositions();

    _py_self.attr("finish_update")();

    //process results from TF
    //TODO: Handle virial (See TablePotential.cc?)
     ArrayHandle<Scalar4> h_force(m_force, access_location::host);
    memcpy(h_force.data, _input_buffer, sizeof(Scalar4) * _buffer_size);

    if (m_prof) m_prof->pop();
}

void TensorflowUpdater::sendPositions() {
    // access the particle data for writing on the CPU
    assert(m_pdata);
    assert(m_pdata->getN() == _buffer_size);
    ArrayHandle<Scalar4> h_pos(m_pdata->getPositions(), access_location::host, access_mode::read);

    //send data to buffer
    memcpy(_output_buffer, h_pos.data, sizeof(Scalar4) * _buffer_size);
}

void TensorflowUpdater::sendNeighbors() {

    //These snippets taken from md/TablePotentials.cc

    // start by updating the neighborlist
    m_nlist->compute(timestep);

    if (m_prof) m_prof->push("TensorflowUpdater::sendNeighbors");

    // depending on the neighborlist settings, we can take advantage of newton's third law
    // to reduce computations at the cost of memory access complexity: set that flag now
    bool third_law = m_nlist->getStorageMode() == NeighborList::half;

    // access the neighbor list
    ArrayHandle<unsigned int> h_n_neigh(m_nlist->getNNeighArray(), access_location::host, access_mode::read);
    ArrayHandle<unsigned int> h_nlist(m_nlist->getNListArray(), access_location::host, access_mode::read);
    ArrayHandle<unsigned int> h_head_list(m_nlist->getHeadList(), access_location::host, access_mode::read);

    // for each particle
    for (int i = 0; i < (int) m_pdata->getN(); i++) {
        // access the particle's position and type (MEM TRANSFER: 4 scalars)
        Scalar3 pi = make_scalar3(h_pos.data[i].x, h_pos.data[i].y, h_pos.data[i].z);
        unsigned int typei = __scalar_as_int(h_pos.data[i].w);
        const unsigned int head_i = h_head_list.data[i];

        // loop over all of the neighbors of this particle
        const unsigned int size = (unsigned int)h_n_neigh.data[i];
        for (unsigned int j = 0; j < size; j++)
            {
            // access the index of this neighbor
            unsigned int k = h_nlist.data[head_i + j];
            // sanity check
            assert(k < m_pdata->getN() + m_pdata->getNGhosts());

            // calculate dr
            Scalar3 pk = make_scalar3(h_pos.data[k].x, h_pos.data[k].y, h_pos.data[k].z);
            Scalar3 dx = pi - pk;

            // access the type of the neighbor particle
            unsigned int typej = __scalar_as_int(h_pos.data[k].w);
            // sanity check
            assert(typej < m_pdata->getNTypes());

            // apply periodic boundary conditions
            dx = box.minImage(dx);

            // access needed parameters
            unsigned int cur_table_index = table_index(typei, typej);
            Scalar4 params = h_params.data[cur_table_index];
            Scalar rmin = params.x;
            Scalar rmax = params.y;
            Scalar delta_r = params.z;

            // start computing the force
            Scalar rsq = dot(dx, dx);
            Scalar r = sqrt(rsq);

            // only compute the force if the particles are within the region defined by V


    if (m_prof) m_prof->pop("TensorflowUpdater::sendNeighbors");
}

std::vector<Scalar4> TensorflowUpdater::get_input_array() const {
    std::vector<Scalar4> array(_input_buffer, _input_buffer + _buffer_size);
    return array;
}

std::vector<Scalar4> TensorflowUpdater::get_output_array() const {
    std::vector<Scalar4> array(_output_buffer, _output_buffer + _buffer_size);
    return array;
}

/* Export the CPU updater to be visible in the python module
 */
void export_TensorflowUpdater(pybind11::module& m)
    {
    pybind11::class_<TensorflowUpdater, std::shared_ptr<TensorflowUpdater> >(m, "TensorflowUpdater", pybind11::base<ForceCompute>())
        .def(pybind11::init<std::shared_ptr<SystemDefinition>, pybind11::object &>())
        .def("get_input_buffer", &TensorflowUpdater::get_input_buffer, pybind11::return_value_policy::reference)
        .def("get_output_buffer", &TensorflowUpdater::get_output_buffer, pybind11::return_value_policy::reference)
        .def("get_input_array", &TensorflowUpdater::get_input_array, pybind11::return_value_policy::take_ownership)
        .def("get_output_array", &TensorflowUpdater::get_output_array, pybind11::return_value_policy::take_ownership)
    ;
    }

// ********************************
// here follows the code for TensorflowUpdater on the GPU

#ifdef ENABLE_CUDA

/*! \param sysdef System to zero the velocities of
*/
TensorflowUpdaterGPU::TensorflowUpdaterGPU(std::shared_ptr<SystemDefinition> sysdef, pybind11::object py_self)
        : TensorflowUpdater(sysdef, py_self)
    {
    }


/*! Perform the needed calculations to zero the system's velocity
    \param timestep Current time step of the simulation
*/
void TensorflowUpdaterGPU::update(unsigned int timestep)
    {
    if (m_prof) m_prof->push("TensorflowUpdater");

    // access the particle data arrays for writing on the GPU
    ArrayHandle<Scalar4> d_vel(m_pdata->getVelocities(), access_location::device, access_mode::readwrite);

    // call the kernel devined in TensorflowUpdater.cu
    gpu_zero_velocities(d_vel.data, _buffer_size);

    // check for error codes from the GPU if error checking is enabled
    if(m_exec_conf->isCUDAErrorCheckingEnabled())
        CHECK_CUDA_ERROR();

    if (m_prof) m_prof->pop();
    }

/* Export the GPU updater to be visible in the python module
 */
void export_TensorflowUpdaterGPU(pybind11::module& m)
    {
    pybind11::class_<TensorflowUpdaterGPU, std::shared_ptr<TensorflowUpdaterGPU> >(m, "TensorflowUpdaterGPU", pybind11::base<TensorflowUpdater>())
        .def(pybind11::init<std::shared_ptr<SystemDefinition>, pybind11::object &>())
        .def("get_input_buffer", &TensorflowUpdater::get_input_buffer)
        .def("get_output_buffer", &TensorflowUpdater::get_output_buffer)
    ;
    }

#endif // ENABLE_CUDA
