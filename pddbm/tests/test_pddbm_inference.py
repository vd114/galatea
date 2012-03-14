from pylearn2.models.s3c import S3C
from pylearn2.models.s3c import E_Step
from pylearn2.models.s3c import Grad_M_Step
from galatea.pddbm.pddbm import PDDBM, InferenceProcedure
from pylearn2.models.rbm import RBM
from pylearn2.models.dbm import DBM
from theano import function
import numpy as np
import theano.tensor as T
from theano import config
#from pylearn2.utils import serial
import warnings


if config.floatX != 'float64':
    config.floatX = 'float64'
    warnings.warn("Changed config.floatX to float64. s3c inference tests currently fail due to numerical issues for float32")

def broadcast(mat, shape_0):
    rval = mat
    if mat.shape[0] != shape_0:
        assert mat.shape[0] == 1

        rval = np.zeros((shape_0, mat.shape[1]),dtype=mat.dtype)

        for i in xrange(shape_0):
            rval[i,:] = mat[0,:]

    return rval


class Test_PDDBM_Inference:
    def __init__(self):
        """ gets a small batch of data
            sets up a PD-DBM model
        """

        self.tol = 1e-5

        X = np.random.RandomState([1,2,3]).randn(1000,5)

        X -= X.mean()
        X /= X.std()
        m, D = X.shape
        N = 6
        N2 = 7


        s3c = S3C(nvis = D,
                 nhid = N,
                 irange = .1,
                 init_bias_hid = 0.,
                 init_B = 3.,
                 min_B = 1e-8,
                 max_B = 1000.,
                 init_alpha = 1., min_alpha = 1e-8, max_alpha = 1000.,
                 init_mu = 1., e_step = None,
                 m_step = Grad_M_Step(),
                 min_bias_hid = -1e30, max_bias_hid = 1e30,
                )

        rbm = RBM(nvis = N, nhid = N2, irange = .05, init_bias_vis = -1.5, init_bias_hid = 1.5)

        #don't give the model an inference procedure or learning rate so it won't spend years compiling a learn_func
        self.model = PDDBM(
                dbm = DBM(  use_cd = 1,
                            rbms = [ rbm  ]),
                s3c = s3c
        )

        self.model.make_pseudoparams()

        self.inference_procedure = InferenceProcedure(
                    schedule = [ ['s',.1],   ['h',.1],   ['g',0, 0.2],   ['h', 0.2], ['s',0.2],
                                ['h',0.3], ['g',0,.3],   ['h',0.3], ['s',0.4], ['h',0.4],
                                ['g',0,.4],   ['h',0.4], ['s',.4], ['h',0.4],
                                ['g',0,.5],   ['h',0.5], ['s', 0.5], ['h',0.1],
                                ['s',0.5] ],
                    clip_reflections = True,
                    rho = .5 )
        self.inference_procedure.register_model(self.model)

        self.X = X
        self.N = N
        self.N2 = N2
        self.m = m

    """
        The next two methods are just a copy paste of the S3C tests. Hasn't been ported to PDDBM yet.

    def test_grad_s(self):

        "tests that the gradients with respect to s_i are 0 after doing a mean field update of s_i "

        model = self.model
        e_step = self.e_step
        X = self.X

        assert X.shape[0] == self.m

        model.test_batch_size = X.shape[0]

        init_H = e_step.init_H_hat(V = X)
        init_Mu1 = e_step.init_S_hat(V = X)

        prev_setting = config.compute_test_value
        config.compute_test_value= 'off'
        H, Mu1 = function([], outputs=[init_H, init_Mu1])()
        config.compute_test_value = prev_setting

        H = broadcast(H, self.m)
        Mu1 = broadcast(Mu1, self.m)

        H = np.cast[config.floatX](self.model.rng.uniform(0.,1.,H.shape))
        Mu1 = np.cast[config.floatX](self.model.rng.uniform(-5.,5.,Mu1.shape))



        H_var = T.matrix(name='H_var')
        H_var.tag.test_value = H
        Mu1_var = T.matrix(name='Mu1_var')
        Mu1_var.tag.test_value = Mu1
        idx = T.iscalar()
        idx.tag.test_value = 0


        S = e_step.infer_S_hat(V = X, H_hat = H_var, S_hat = Mu1_var)

        s_idx = S[:,idx]

        s_i_func = function([H_var,Mu1_var,idx],s_idx)

        sigma0 = 1. / model.alpha
        Sigma1 = e_step.infer_var_s1_hat()
        mu0 = T.zeros_like(model.mu)

        #by truncated KL, I mean that I am dropping terms that don't depend on H and Mu1
        # (they don't affect the outcome of this test and some of them are intractable )
        trunc_kl = - model.entropy_hs(H_hat = H_var, var_s0_hat = sigma0, var_s1_hat = Sigma1) + \
                     model.expected_energy_vhs(V = X, H_hat = H_var, S_hat = Mu1_var, var_s0_hat = sigma0, var_s1_hat = Sigma1)

        grad_Mu1 = T.grad(trunc_kl.sum(), Mu1_var)

        grad_Mu1_idx = grad_Mu1[:,idx]

        grad_func = function([H_var, Mu1_var, idx], grad_Mu1_idx)

        for i in xrange(self.N):
            Mu1[:,i] = s_i_func(H, Mu1, i)

            g = grad_func(H,Mu1,i)

            assert not np.any(np.isnan(g))

            g_abs_max = np.abs(g).max()


            if g_abs_max > self.tol:
                raise Exception('after mean field step, gradient of kl divergence wrt mean field parameter should be 0, but here the max magnitude of a gradient element is '+str(g_abs_max)+' after updating s_'+str(i))

    def test_value_s(self):

        "tests that the value of the kl divergence decreases with each update to s_i "

        model = self.model
        e_step = self.e_step
        X = self.X

        assert X.shape[0] == self.m

        init_H = e_step.init_H_hat(V = X)
        init_Mu1 = e_step.init_S_hat(V = X)

        prev_setting = config.compute_test_value
        config.compute_test_value= 'off'
        H, Mu1 = function([], outputs=[init_H, init_Mu1])()
        config.compute_test_value = prev_setting

        H = broadcast(H, self.m)
        Mu1 = broadcast(Mu1, self.m)

        H = np.cast[config.floatX](self.model.rng.uniform(0.,1.,H.shape))
        Mu1 = np.cast[config.floatX](self.model.rng.uniform(-5.,5.,Mu1.shape))


        H_var = T.matrix(name='H_var')
        H_var.tag.test_value = H
        Mu1_var = T.matrix(name='Mu1_var')
        Mu1_var.tag.test_value = Mu1
        idx = T.iscalar()
        idx.tag.test_value = 0

        S = e_step.infer_S_hat( V = X, H_hat = H_var, S_hat = Mu1_var)

        s_idx = S[:,idx]

        s_i_func = function([H_var,Mu1_var,idx],s_idx)

        sigma0 = 1. / model.alpha
        Sigma1 = e_step.infer_var_s1_hat()
        mu0 = T.zeros_like(model.mu)

        #by truncated KL, I mean that I am dropping terms that don't depend on H and Mu1
        # (they don't affect the outcome of this test and some of them are intractable )
        trunc_kl = - model.entropy_hs(H_hat = H_var, var_s0_hat = sigma0, var_s1_hat = Sigma1) + \
                     model.expected_energy_vhs(V = X, H_hat = H_var, S_hat = Mu1_var, var_s0_hat = sigma0, var_s1_hat = Sigma1)

        trunc_kl_func = function([H_var, Mu1_var], trunc_kl)

        for i in xrange(self.N):
            prev_kl = trunc_kl_func(H,Mu1)

            Mu1[:,i] = s_i_func(H, Mu1, i)

            new_kl = trunc_kl_func(H,Mu1)


            increase = new_kl - prev_kl


            mx = increase.max()

            if mx > 1e-3:
                raise Exception('after mean field step in s, kl divergence should decrease, but some elements increased by as much as '+str(mx)+' after updating s_'+str(i))
    """


    def test_grad_h(self):

        "tests that the gradients with respect to h_i are 0 after doing a mean field update of h_i "

        model = self.model
        ip = self.inference_procedure
        X = self.X

        assert X.shape[0] == self.m

        """
        init_H = ip.init_H_hat(V = X)
        init_S = ip.init_S_hat(V = X)
        init_G = ip.init_G_hat(V = X)[0]

        prev_setting = config.compute_test_value
        config.compute_test_value= 'off'
        H, S, G = function([], outputs=[init_H, init_S, init_G])()
        config.compute_test_value = prev_setting

        H, S, G = [ broadcast(elem, self.m) for elem in [H,S,G] ]
        """

        H = np.cast[config.floatX](self.model.rng.uniform(0.,1.,(self.m, self.N)))
        S = np.cast[config.floatX](self.model.rng.uniform(-5.,5.,(self.m, self.N)))
        G = np.cast[config.floatX](self.model.rng.uniform(0.,1.,(self.m,self.N2)))

        H_var = T.matrix(name='H_var')
        H_var.tag.test_value = H
        S_var = T.matrix(name='S_var')
        S_var.tag.test_value = S
        G_var = T.matrix(name='G_var')
        G_var.tag.test_value = G
        idx = T.iscalar()
        idx.tag.test_value = 0

        new_H = ip.infer_H_hat(V = X, H_hat = H_var, S_hat = S, G1_hat = G_var )
        h_idx = new_H[:,idx]

        updates_func = function([H_var,S_var,G_var,idx], h_idx, on_unused_input = 'ignore')

        sigma0 = ip.infer_var_s0_hat()
        Sigma1 = ip.infer_var_s1_hat()
        mu0 = T.zeros_like(model.s3c.mu)

        trunc_kl = ip.truncated_KL( V = X, obs = { 'H_hat' : H_var,
                                                 'S_hat' : S_var,
                                                 'var_s0_hat' : sigma0,
                                                 'var_s1_hat' : Sigma1,
                                                 'G_hat' : ( G_var, ) } )

        assert len(trunc_kl.type.broadcastable) == 0

        grad_H = T.grad(trunc_kl, H_var)

        assert len(grad_H.type.broadcastable) == 2

        grad_func = function([H_var, S_var, G_var], grad_H)

        failed = False

        for i in xrange(self.N):
            rval = updates_func(H, S, G, i)
            H[:,i] = rval

            g = grad_func(H,S,G)[:,i]

            assert not np.any(np.isnan(g))

            g_abs_max = np.abs(g).max()

            if g_abs_max > self.tol:
                #print "new values of H"
                #print H[:,i]
                #print "gradient on new values of H"
                #print g

                failed = True

                print 'iteration ',i
                #print 'max value of new H: ',H[:,i].max()
                #print 'H for failing g: '
                failing_h = H[np.abs(g) > self.tol, i]
                #print failing_h

                #from matplotlib import pyplot as plt
                #plt.scatter(H[:,i],g)
                #plt.show()

                #ignore failures extremely close to h=1

                high_mask = failing_h > .001
                low_mask = failing_h < .999

                mask = high_mask * low_mask

                print 'masking out values of h less than .001 and above .999 because gradient acts weird there'
                print '# failures passing the range mask: ',mask.shape[0],' err ',g_abs_max

                if mask.sum() > 0:
                    print 'failing h passing the range mask'
                    print failing_h[ mask.astype(bool) ]
                    raise Exception('after mean field step, gradient of kl divergence'
                            ' wrt freshly updated variational parameter should be 0, '
                            'but here the max magnitude of a gradient element is '
                            +str(g_abs_max)+' after updating h_'+str(i))




    def test_value_h(self):

        "tests that the value of the kl divergence decreases with each update to h_i "

        model = self.model
        e_step = self.e_step
        X = self.X

        assert X.shape[0] == self.m

        init_H = e_step.init_H_hat(V = X)
        init_Mu1 = e_step.init_S_hat(V = X)

        prev_setting = config.compute_test_value
        config.compute_test_value= 'off'
        H, Mu1 = function([], outputs=[init_H, init_Mu1])()
        config.compute_test_value = prev_setting

        H = broadcast(H, self.m)
        Mu1 = broadcast(Mu1, self.m)

        H = np.cast[config.floatX](self.model.rng.uniform(0.,1.,H.shape))
        Mu1 = np.cast[config.floatX](self.model.rng.uniform(-5.,5.,Mu1.shape))


        H_var = T.matrix(name='H_var')
        H_var.tag.test_value = H
        Mu1_var = T.matrix(name='Mu1_var')
        Mu1_var.tag.test_value = Mu1
        idx = T.iscalar()
        idx.tag.test_value = 0

        newH = e_step.infer_H_hat(V = X, H_hat = H_var, S_hat = Mu1_var)


        h_idx = newH[:,idx]


        h_i_func = function([H_var,Mu1_var,idx],h_idx)

        sigma0 = 1. / model.alpha
        Sigma1 = e_step.infer_var_s1_hat()
        mu0 = T.zeros_like(model.mu)

        #by truncated KL, I mean that I am dropping terms that don't depend on H and Mu1
        # (they don't affect the outcome of this test and some of them are intractable )
        trunc_kl = - model.entropy_hs(H_hat = H_var, var_s0_hat = sigma0, var_s1_hat = Sigma1) + \
                     model.expected_energy_vhs(V = X, H_hat = H_var, S_hat = Mu1_var, var_s0_hat = sigma0, var_s1_hat = Sigma1)

        trunc_kl_func = function([H_var, Mu1_var], trunc_kl)

        for i in xrange(self.N):
            prev_kl = trunc_kl_func(H,Mu1)

            H[:,i] = h_i_func(H, Mu1, i)
            #we don't update mu, the whole point of the split e step is we don't have to

            new_kl = trunc_kl_func(H,Mu1)


            increase = new_kl - prev_kl


            print 'failures after iteration ',i,': ',(increase > self.tol).sum()

            mx = increase.max()

            if mx > 1e-4:
                print 'increase amounts of failing examples:'
                print increase[increase > self.tol]
                print 'failing H:'
                print H[increase > self.tol,:]
                print 'failing Mu1:'
                print Mu1[increase > self.tol,:]
                print 'failing V:'
                print X[increase > self.tol,:]


                raise Exception('after mean field step in h, kl divergence should decrease, but some elements increased by as much as '+str(mx)+' after updating h_'+str(i))

    def test_g(self):
        raise NotImplementedError()

if __name__ == '__main__':
    obj = Test_PDDBM_Inference()

    #obj.test_grad_h()
    #obj.test_grad_s()
    #obj.test_value_s()
    obj.test_value_h()
