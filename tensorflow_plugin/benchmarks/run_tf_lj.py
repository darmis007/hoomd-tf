import hoomd, hoomd.md, math
import hoomd.tensorflow_plugin

model_dir = '/tmp/benchmark-lj-potential-model'
with hoomd.tensorflow_plugin.tfcompute(model_dir) as tfcompute:
    N = 2**14
    rcut = 3.0
    hoomd.context.initialize()
    system = hoomd.init.create_lattice(unitcell=hoomd.lattice.sq(a=1.0),
                                    n=int(math.ceil(N**(1/2))))
    nlist = hoomd.md.nlist.cell()
    hoomd.md.integrate.mode_standard(dt=0.005)
    hoomd.md.integrate.nve(group=hoomd.group.all()).randomize_velocities(seed=1, kT=1)
    #lj = hoomd.md.pair.lj(r_cut=3.0, nlist=nlist)
    #lj.pair_coeff.set('A', 'A', epsilon=1.0, sigma=1.0)
    tfcompute.attach(nlist, r_cut=rcut)
    hoomd.run(1000, profile=True)
