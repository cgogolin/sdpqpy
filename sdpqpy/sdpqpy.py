# -*- coding: utf-8 -*-
"""
This module provides a set of classes to more comfortably work with
quantum lattice models in the context of ncpol2sdpa.

@author: Christian Gogolin, Peter Wittek
"""
from __future__ import print_function, division
import cmath
import csv
import math
import os
import pickle
import time
from abc import ABCMeta, abstractmethod

from sympy.physics.quantum import Dagger
from ncpol2sdpa import RdmHierarchy, get_neighbors, get_next_neighbors, \
                       generate_variables, bosonic_constraints, flatten, \
                       fermionic_constraints


def write_array(filename, array):
    file_ = open(filename, 'w')
    writer = csv.writer(file_)
    writer.writerow(array)
    file_.close()


class LatticeModel:
    """A class to represent an abstract quantum lattice model whose Hamiltonian
    problem is to be solved with ncpol2sdpa.
    """
    __metaclass__ = ABCMeta

    def __init__(self, lattice_length, lattice_width, solver, outputDir):
        self._lattice_length = lattice_length
        self._lattice_width = lattice_width
        self._solver = solver
        self._outputDir = outputDir
        self._substitutions = None
        self.__sdpRelaxation = None
        self.__outdatedSdpRelaxation = None
        self.__hamiltonian = None

    @abstractmethod
    def getSuffix(self):
        """To be overwritten by any subclasses such that it returns a suffix
        with sufficient information to uniquely identify a concrete instance
        of the Model including all constrains and paramters.
        """
        pass

    @abstractmethod
    def getShortSuffix(self):
        """To be overwritten by any subclasses such that it returns a suffix
        with sufficient information to uniquely identify the a class of
        instances of the Model wholse sdpRelaxations can be transformed into
        each other via process constrains.
        """
        pass

    @abstractmethod
    def createSubstitutions(self):
        """To be overwritten by any subclasses. Should return the, for example,
        bosonic or fermionic substitution rules appropriate for the model.
        """
        pass

    @abstractmethod
    def createMonomials(self):
        """To be overwritten by any subclasses. Should return a list of
        lists of polynomials in the operator algebra, each corresponding to a
        block in the moment matrix."""
        pass

    @abstractmethod
    def createHamiltonian(self):
        """To be overwritten by any subclasses. Should return the Hamiltonian
        in a form suitable for sdpRelaxation.set_objective()."""
        pass

    @abstractmethod
    def createSdp(self, outdatedSdpRelaxation=None):
        """To be overwritten by any subclasses. Should return a suitable SDP.
        """
        pass

    # @abstractmethod
    # def pickleFile(self):
    #     """To be overwritten by any subclasses. Should return a suitable
    #     path to which the SDP is pickled and/or loaded.
    #     """
    #     pass

    def pickleSdp(self, sdpRelaxation):
        """Pickles the sdpRelaxation. If the sdpRelaxation is still unsolved
        is writes to a path derived from getShortSuffix() if it is a complete
        instance including constrains and a solution it writes to a path
        derived from getSuffix().
        """
        if self._outputDir is not None:
            if not os.path.isdir(self._outputDir):
                os.mkdir(self._outputDir)

            if sdpRelaxation.status == "unsolved":
                with open(self._outputDir + "/" +"sdpRelaxation" +
                          self.getShortSuffix() + ".pickle", 'wb') as handle:
                    pickle.dump(sdpRelaxation, handle)
            else:
                with open(self._outputDir + "/" +"sdpRelaxation" +
                          self.getSuffix() + ".pickle", 'wb') as handle:
                    pickle.dump(sdpRelaxation, handle)

    def loadSdp(self):
        """Tries to load an SDP, first it tries to find an already solved
        instance stored under a path derived from getSuffix(), if this fails
        it tries to load a more general instance stored under a path derived
        from getShortSuffix().
        """
        try:
            with open(self._outputDir + "/" +"sdpRelaxation" +
                      self.getSuffix() + ".pickle", 'rb') as handle:
                return pickle.load(handle)
        except (KeyboardInterrupt, SystemExit):
            raise 
        except:
            with open(self._outputDir + "/" +"sdpRelaxation" +
                      self.getShortSuffix() + ".pickle", 'rb') as handle:
                return pickle.load(handle)

    def getSubstitutions(self):
        """Cached getter mehtod that calls createSubsitutions() if necessary.
        """
        if self._substitutions is None:
            self._substitutions = self.createSubstitutions()
        return self._substitutions

    def getSdp(self):
        """Cached getter method that calls createSdp() if necessary.
        """
        if self.__sdpRelaxation is None:
            if self.__outdatedSdpRelaxation is None:
                self.__sdpRelaxation = self.createSdp()
            else:
                self.__sdpRelaxation = \
                    self.createSdp(self.__outdatedSdpRelaxation)
            self.pickleSdp(self.__sdpRelaxation)
        return self.__sdpRelaxation

    def getMonomials(self):
        """Returns the set of monomials.
        """
        return self.getSdp().monomial_sets

    def invalidateSolution(self):
        """Invalidates the stored solution. This function is mainly for
        intermal use and is caled for example when the paramters of the system
        are changed.
        """
        if self.__sdpRelaxation is not None:
            self.__sdpRelaxation.status = "unsolved"

    def invalidateSdp(self):
        """Deletes the SDP and its solution (if present) so that it is updated
        or regenerted from the set parameters during the next call to getSdp().
        The now invalid SDP is saved in self.__outdatedSdpRelaxation to enable
        a posible speed up in createSdp(), which is called by getSdp().
        """
        if self.__sdpRelaxation is not None:
            self.__outdatedSdpRelaxation = self.__sdpRelaxation
            self.__sdpRelaxation = None
        self.invalidateSolution()

    def getXMat(self):
        """Returns the moment matrix that was the result of solving the
        specified SDP. If necessary the SDP is solved first.
        """
        if self.__sdpRelaxation is None or self.__sdpRelaxation.x_mat is None:
            self.solve()
        return self.__sdpRelaxation.x_mat

    def getYMat(self):
        """Returns the moment matrix that was the result of solving the
        specified SDP. If necessary the SDP is solved first.
        """
        if self.__sdpRelaxation is None or self.__sdpRelaxation.y_mat is None:
            self.solve()
        return self.__sdpRelaxation.y_mat

    def getPrimal(self):
        """Returns the primal. If necessary the SDP is solved first.
        """
        if self.__sdpRelaxation is None or self.__sdpRelaxation.primal is None:
            self.solve()
        return self.__sdpRelaxation.primal

    def getDual(self):
        """Returns the dual. If necessary the SDP is solved first.
        """
        if self.__sdpRelaxation is None or self.__sdpRelaxation.dual is None:
            self.solve()
        return self.__sdpRelaxation.dual

    def getGap(self):
        """Returns the gap between the primal and the dual solution. If
        necessary the SDP is solved first.
        """
        return self.getPrimal() - self.getDual()

    def getHamiltonian(self):
        """Cached getter mehtod that calls createHamiltonian() if necessary.
        """
        if self.__hamiltonian is None:
            self.__hamiltonian = self.createHamiltonian()
        return self.__hamiltonian

    def invalidateHamiltonian(self):
        """Deletes the cached Hamiltonian so that it is regenerted from the set
        parameters during the next call to getHamiltonian().
        """
        self.invalidateSdp()
        self.__hamiltonian = None

    def solve(self):
        """Genrates and solves the SDP representing the specified model. It
        first tries to load an apropriate possibly already solved SDP from a
        picke file in self._outputDir. If this fails if calls getSdp() and
        then soves it.
        """
        self.getSdp()  # sets self.__sdpRelaxation

        if self.__sdpRelaxation.status == "unsolved":

            self.__sdpRelaxation.set_objective(self.getHamiltonian())

            print('solving SDP with '+str(self._solver))
            time0 = time.time()
            self.__sdpRelaxation.solve(solver=self._solver)
            print("SDP solved in", time.time()-time0, "seconds")

            self.pickleSdp(self.__sdpRelaxation)

    def getEnergy(self):
        """Returns the energy (primal of the SDP) of the system.
        """
        return self.getPrimal()

    def getSize(self):
        """Returns the total size (volume) of the system.
        """
        return self._lattice_length * self._lattice_width

    def getLength(self):
        """Returns the length of the system.
        """
        return self._lattice_length

    def getWidth(self):
        """Returns the width of the system.
        """
        return self._lattice_width


class SecondQuantizedModel(LatticeModel):
    """A class to represent an abstract quantum lattice model in the language
    of second quantization that is to be solved by ncpol2sdpa. Note that
    periodic can be either True/False, or 0,1,-1, where False and 0 correspond
    to open boundary conditins, True and 1 to periodic and -1 to antiperiodic.
    """
    __metaclass__ = ABCMeta

    def __init__(self, lattice_length, lattice_width, solver, outputDir,
                 periodic, window_length):
        LatticeModel.__init__(self, lattice_length, lattice_width, solver,
                              outputDir)
        self._b = generate_variables('b', lattice_length * lattice_width,
                                     commutative=False)
        self._level = -1
        self._periodic = periodic
        self.nmax = None
        self.localNmax = None
        self.n = None
        self.nmin = None
        if window_length == 0:
            self.window_length = lattice_length
        else:
            self.window_length = window_length

    def createSdp(self, outdatedSdpRelaxation=None):
        """Retuns an appropriate SDP representing a relaxation of the specified
        Hamiltonian problem. It first tries to load a pickled SDP.
        If this fails it generates a new SDP.
        """
        sdpRelaxation = None
        print('trying to load pickled SDP for %dx%d lattice' %
              (self._lattice_length, self._lattice_width))
        try:
            sdpRelaxation = self.loadSdp()
            if sdpRelaxation is not None and \
                    sdpRelaxation.status != "unsolved":
                # We assume that we got a solved instance with all paramters
                # correctly set and return that
                print('succesfully loaded a solved SDP')
                return sdpRelaxation
            else:
                print('succesfully loaded an unsolved SDP')
        except (KeyboardInterrupt, SystemExit):
            raise 
        except (IOError, EOFError):
            print('no pickled SDP found, generating SDP')

        if sdpRelaxation is None:
            sdpRelaxation = outdatedSdpRelaxation

        equalities = []
        inequalities = []
        momentinequalities = []
        if self.localNmax is not None:
            inequalities.extend(self.localNmax-Dagger(br)*br
                                for br in self._b)
        if self.n is not None:
            momentinequalities.append(self.n-sum(Dagger(br)*br
                                                 for br in self._b))
            momentinequalities.append(sum(Dagger(br)*br
                                          for br in self._b)-self.n)

            for fr in self._b:
                # momentinequalities.append((fr*self.n-fr*sum(Dagger(br)*br for br in self._b)))
                # momentinequalities.append((Dagger(fr)*sum(Dagger(br)*br for br in self._b)-Dagger(fr)*self.n))
                op1 = Dagger(fr)*fr
                op2 = fr*Dagger(fr)
                momentinequalities.append((op1*self.n-op1*sum(Dagger(br)*br for br in self._b)))
                momentinequalities.append((op1*sum(Dagger(br)*br for br in self._b)-op1*self.n))
                momentinequalities.append((op2*self.n-op2*sum(Dagger(br)*br for br in self._b)))
                momentinequalities.append((op2*sum(Dagger(br)*br for br in self._b)-op2*self.n))


        if self.nmax is not None:
            momentinequalities.append(self.nmax-sum(Dagger(br)*br for br in self._b))
        if self.nmin is not None:
            momentinequalities.append(sum(Dagger(br)*br for br in self._b)-self.nmin)

        try:
            # Try to recycle the outdated or loaded SDP this only works if if
            # sdpRelaxation is not None and the number of constaints matches
            print("trying to recycle an old solution")
            sdpRelaxation.process_constraints(equalities=equalities,
                                              inequalities=inequalities,
                                              momentinequalities=momentinequalities)
            print("succesfully recycled an old solution")
        except (KeyboardInterrupt, SystemExit):
            raise 
        except:
            #We have to generate from scatch
            time0 = time.time()
            sdpRelaxation = RdmHierarchy(self._b, verbose=1)
            if self._level == -1:
                print("creating custom monomial vectors as level is " +
                      str(self._level))
                monomials = self.createMonomials()
            else:
                print("generating a standard SDP with level " +
                      str(self._level))
                monomials = None

            sdpRelaxation.get_relaxation(self._level,
                                         equalities=equalities,
                                         inequalities=inequalities,
                                         momentinequalities=momentinequalities,
                                         substitutions=self.getSubstitutions(),
                                         extramonomials=monomials)
            print('SDP of lattice %dx%d generated in %0.2f seconds' %
                  (self._lattice_length, self._lattice_width,
                   (time.time()-time0)))

        return sdpRelaxation

    def setLevel(self, level):
        """Sets the level of the relaxation and thereby prevents generation of
        the monomials with the customizable createMonomials() method."""
        self.invalidateSdp()
        self._level = level

    def getDensityDensityCorrelations(self):
        """Returns the density density correlation function. If necessary
        soles the SDP first.
        """
        if self._lattice_width != 1:
            raise Exception("More than 1D not implemented!")

        if self._periodic or self._periodic == 1:
            bext = self._b + [bi for bi in self._b]
        elif self._periodic == -1:
            bext = self._b + [-bi for bi in self._b]
        else:
            bext = self._b

        def f(r):
            Cr = 0
            L = len(self._b)
            for l in range(L):
                if (self._periodic is False or self._periodic == 0) and \
                        l+r >= L:
                    break
                n_lr = Dagger(bext[l+r])*bext[l+r]
                n_l = Dagger(bext[l])*bext[l]
                en_l = self.expectationValue(n_l)
                en_lr = self.expectationValue(n_lr)
                en_lrl = self.expectationValue(n_lr*n_l)
                Cr += en_lrl - en_lr*en_l
            return Cr/L

        return [f(r) for r in range(0, self._lattice_length)]

    def gtwo(self):
        """Returns the g_2 function. If necessary soles the SDP first.
        """
        if self._lattice_width != 1:
            raise Exception("More than 1D not implemented!")

        if self._periodic or self._periodic == 1:
            bext = self._b + [bi for bi in self._b]
        elif self._periodic == -1:
            bext = self._b + [-bi for bi in self._b]
        else:
            bext = self._b

        def f(r):
            Cr = 0
            L = len(self._b)
            l = 0
            if (self._periodic is False or self._periodic == 0) and l+r >= L:
                return 0
            n_lr = Dagger(bext[l+r])*bext[l+r]
            n_l = Dagger(bext[l])*bext[l]
            en_l = self.expectationValue(n_l)
            en_lr = self.expectationValue(n_lr)
            en_lrl = self.expectationValue(n_lr*n_l)
            Cr += en_lrl - en_lr*en_l
            return Cr

        return [f(r) for r in range(0, self._lattice_length)]

    def getMomentumDistribution(self):
        """Returns the momentum distribution. If necessary soles the SDP first.
        """
        def f(k):
            n = 0
            for j, bj in enumerate(self._b):
                for l, bl in enumerate(self._b):
                    n += cmath.exp(1j*k*(j-l))*self.expectationValue(Dagger(bj)*bl)
            return n/len(self._b)
        return [f(2*cmath.pi*m/self._lattice_length)
                for m in range(-int(self._lattice_length/2),
                               int(self._lattice_length/2+1))]

    def getParticleNumber(self):
        """Returns the total particle number. If necessary soles the SDP first.
        """
        return self.expectationValue(sum( Dagger(bj)*bj for bj in self._b))

    def expectationValue(self, operator):
        """Returns the expectation value of the given operator. If necessary
        soles the SDP first.
        """
        if self.getSdp() is None or self.getSdp().status == "unsolved":
            self.solve()
        return self.getSdp()[operator]

    def getPhysicalQuantities(self):
        """Returns a dictionaly of names and corresponding functions of all
        physical quantities that are to be written in writeData(). This should
        be overwritten in subclasses.
        """
        return {"/gtwo": self.gtwo(),
                "/density_density_corr": self.getDensityDensityCorrelations(),
                "/momentum_distr": self.getMomentumDistribution(),
                "/particle_number": [self.getParticleNumber()],
                "/primal": [self.getPrimal()],
                "/dual": [self.getPrimal()]}

    def writeData(self):
        """Writes the values of all physical quantities returned by
        getPhysicalQuantities() to the respective files.
        """
        for key, data in iter(self.getPhysicalQuantities().items()):
            write_array(self._outputDir + key + self.getSuffix() + ".csv",
                        data)

    def getShortSuffix(self):
        suffix = "_lat=" + str(self._lattice_length) + "x" + \
                 str(self._lattice_width)
        if self._periodic:
            suffix += "_periodic=" + str(self._periodic)
        if self.window_length != self._lattice_length:
            suffix += "_window=" + str(self.window_length)
        suffix += "_level="+str(self._level)
        return suffix

    def setConstraints(self, **kwargs):
        """Sets the specifide constaints. If a constraint was not previously
        set or the value of it was changed it invalidates the cached SDP.
        """
        if "localNmax" in kwargs and self.localNmax != kwargs.get("localNmax"):
            self.invalidateSdp()
            self.localNmax = kwargs.get("localNmax")
        if "n" in kwargs and self.n != kwargs.get("n"):
            self.invalidateSdp()
            self.n = kwargs.get("n")
        if "nmin" in kwargs and self.nmin != kwargs.get("nmin"):
            self.invalidateSdp()
            self.nmin = kwargs.get("nmin")
        if "nmax" in kwargs and self.nmax != kwargs.get("nmax"):
            self.invalidateSdp()
            self.nmax = kwargs.get("nmax")

    def unsetConstraints(self, **kwargs):
        """Unsets the specifide constaints. If a constraint was previously set
        it invalidates the cached SDP.
        """
        if "localNmax" in kwargs and self.localNmax is not None:
            self.localNmax = None
            self.invalidateSdp()
        if "n" in kwargs and self.n is not None:
            self.n = None
            self.invalidateSdp()
        if "nmin" in kwargs and self.nmin is not None:
            self.nmin = None
            self.invalidateSdp()
        if "nmax" in kwargs and self.nmax is not None:
            self.nmax = None
            self.invalidateSdp()


# The following are exemplary implementations of some well known condensed
# matter models:

class BoseHubbardModel(SecondQuantizedModel):
    __metaclass__ = ABCMeta

    def __init__(self, lattice_length, lattice_width, solver, outputDir,
                 periodic=0, window_length=0):
        SecondQuantizedModel.__init__(self, lattice_length, lattice_width,
                                      solver, outputDir, periodic,
                                      window_length)
        self.U = 1
        self.mu = 0
        self.t = 0

    def createHamiltonian(self):
        if self._periodic == -1:
            raise Exception("Antiperiodic boundary conditions not "
                            "implemented!")

        hamiltonian = 0
        for r, br in enumerate(self._b):
            hamiltonian += self.U/2.0*(Dagger(br)*br*(Dagger(br)*br-1))
            if self.mu != 0:
                hamiltonian += -self.mu*Dagger(br)*br
            for s in get_neighbors(r, self._lattice_length,
                                   self._lattice_width, self._periodic):
                hamiltonian += -self.t*(Dagger(br)*self._b[s] +
                                        Dagger(self._b[s])*br)
        return hamiltonian

    def createSubstitutions(self):
        return bosonic_constraints(self._b)

    def createMonomials(self):
        monomials = []
        for i in range(self.getLength() - self.window_length + 1):
            window = self._b[i:i+self.window_length]
            monomials.append([bj*bi for bi in window for bj in window])
            monomials.append([Dagger(bj)*bi for bi in window for bj in window])
            monomials[-1].extend([bj*Dagger(bi)
                                  for bi in window for bj in window])
            monomials.append([Dagger(bj)*Dagger(bi)
                              for bi in window for bj in window])
        return monomials

    def setParameters(self, **kwargs):
        if "mu" in kwargs:
            self.mu = kwargs.get("mu")
            self.invalidateHamiltonian()
        if "t" in kwargs:
            self.t = kwargs.get("t")
            self.invalidateHamiltonian()
        if "U" in kwargs:
            self.U = kwargs.get("U")
            self.invalidateHamiltonian()

    def getSuffix(self):
        suffix = "_lat=" + str(self._lattice_length) + "x" + \
                 str(self._lattice_width) + "_mu=" + str(self.mu) + "_t=" + \
                 str(self.t)
        if self.n is not None:
            suffix += "_n="+str(self.n)
        if self.nmax is not None:
            suffix += "_nmax="+str(self.nmax)
        if self.nmin is not None:
            suffix += "_nmin="+str(self.nmin)
        if self.localNmax is not None:
            suffix += "_localnmax="+str(self.localNmax)
        if self._periodic:
            suffix += "_periodic=" + str(self._periodic)
        if self.window_length != self._lattice_length:
            suffix += "_window=" + str(self.window_length)
        suffix += "_level="+str(self._level)
        return suffix


class FermiHubbardModel(SecondQuantizedModel):
    __metaclass__ = ABCMeta

    def __init__(self, lattice_length, lattice_width, solver, outputDir,
                 periodic=0, window_length=0):
        SecondQuantizedModel.__init__(self, lattice_length, lattice_width,
                                      solver, outputDir, periodic,
                                      window_length)
        self._fu = generate_variables('fu', lattice_length * lattice_width, commutative=False)
        self._fd = generate_variables('fd', lattice_length * lattice_width, commutative=False)
        self._b = flatten([self._fu, self._fd])
        self.mu, self.t, self.h, self.U = 0, 0, 0, 0
        self._periodic = None

    def createHamiltonian(self):
        if self._lattice_width != 1:
            raise Exception("Higher dimension not implemented!")
        elif self._periodic or self._periodic == 1:
            fuext = self._fu + [fi for fi in self._fu]
            fdext = self._fd + [fi for fi in self._fd]
        elif self._periodic == -1:
            fuext = self._fu + [-fi for fi in self._fu]
            fdext = self._fd + [-fi for fi in self._fd]
        else:
            fuext = self._fu
            fdext = self._fd

        hamiltonian = 0
        L = self.getLength()
        if self.t != 0:
            for j in range(L):
                for k in get_neighbors(j, len(fuext), width=1):
                    hamiltonian += -self.t*Dagger(fuext[j])*fuext[k]\
                                   -self.t*Dagger(fuext[k])*fuext[j]
                    hamiltonian += -self.t*Dagger(fdext[j])*fdext[k]\
                                   -self.t*Dagger(fdext[k])*fdext[j]
        if self.U != 0:
            for j in range(L):
                hamiltonian += self.U * (Dagger(fuext[j])*Dagger(fdext[j]) *
                                         fdext[j]*fuext[j])

        if self.h != 0:
            for j in range(L):
                hamiltonian += -self.h/2*(Dagger(fuext[j])*fuext[j] -
                                          Dagger(fdext[j])*fdext[j])

        if self.mu != 0:
            for j in range(L):
                hamiltonian += -self.mu*(Dagger(fuext[j])*fuext[j] +
                                         Dagger(fdext[j])*fdext[j])

        return hamiltonian

    def createSubstitutions(self):
        return fermionic_constraints(self._b)

    def createMonomials(self):
        monomials = []
        for i in range(self.getLength() - self.window_length + 1):
            window = self._b[i:i+self.window_length]
            window.extend(self._b[self.getLength()+i:
                                  self.getLength()+i+self.window_length])
            monomials.append([ci for ci in window])
            monomials[-1].extend([Dagger(ci) for ci in window])
            monomials.append([cj*ci for ci in window for cj in window])
            monomials.append([Dagger(cj)*ci for ci in window for cj in window])
            monomials[-1].extend([cj*Dagger(ci)
                                  for ci in window for cj in window])
            monomials.append([Dagger(cj)*Dagger(ci)
                              for ci in window for cj in window])
        return monomials

    def getMagnetization(self):
        s = 0.5*(sum((Dagger(fu)*fu) for fu in self._fu) -
                 sum((Dagger(fd)*fd) for fd in self._fd))
        return self.expectationValue(s)

    def getParticleNumber(self):
        N = (sum((Dagger(fu)*fu) for fu in self._fu) +
             sum((Dagger(fd)*fd) for fd in self._fd))
        return self.expectationValue(N)

    def setParameters(self, **kwargs):
        if "mu" in kwargs:
            self.mu = kwargs.get("mu")
            self.invalidateHamiltonian()
        if "t" in kwargs:
            self.t = kwargs.get("t")
            self.invalidateHamiltonian()
        if "h" in kwargs:
            self.h = kwargs.get("h")
            self.invalidateHamiltonian()
        if "U" in kwargs:
            self.U = kwargs.get("U")
            self.invalidateHamiltonian()

    def getSuffix(self):
        suffix = "_lat=" + str(self._lattice_length) + "x" + \
                 str(self._lattice_width) + "_periodic=" + str(self._periodic)\
                 + "_mu=" + str(self.mu) + "_t=" + str(self.t) + "_h=" + \
                 str(self.h) + "_U="+str(self.U)
        if self.n is not None:
            suffix += "_n="+str(self.n)
        if self.nmax is not None:
            suffix += "_nmax="+str(self.nmax)
        if self.nmin is not None:
            suffix += "_nmin="+str(self.nmin)
        if self.localNmax is not None:
            suffix += "_localnmax="+str(self.localNmax)
        if self._periodic:
            suffix += "_periodic=" + str(self._periodic)
        if self.window_length != self._lattice_length:
            suffix += "_window=" + str(self.window_length)
        suffix += "_level="+str(self._level)
        return suffix

    def getPhysicalQuantities(self):
        return {"/primal": [self.getPrimal()],
                "/dual": [self.getPrimal()],
                "/magnetization": [self.getMagnetization()]}


class LongRangeQuadraticFermiModel(FermiHubbardModel):
    __metaclass__ = ABCMeta

    def __init__(self, lattice_length, lattice_width, solver, outputDir,
                 periodic=0):
        FermiHubbardModel.__init__(self, lattice_length, lattice_width,
                                   solver, outputDir, periodic,
                                   window_length=0)
        self.mu = 0
        self.t = 0
        self.Delta = 0
        self.alpha = 0

    def createHamiltonian(self):
        if self._lattice_width != 1:
            raise Exception("Higher dimension not implemented!")

        if self._periodic or self._periodic == 1:
            bext = self._b + [bi for bi in self._b]
        elif self._periodic == -1:
            bext = self._b + [-bi for bi in self._b]
        else:
            bext = self._b

        hamiltonian = 0
        for r, br in enumerate(self._b[:self._lattice_length]):
            if self.mu != 0:
                hamiltonian += -self.mu*(Dagger(br)*br-1/2)
            for s in get_neighbors(r, len(bext), self._lattice_width):
                hamiltonian += -self.t*(Dagger(br)*bext[s]+Dagger(bext[s])*br)
            for d in range(1, self._lattice_length):
                for s in get_next_neighbors(r, len(bext), self._lattice_width):
                    hamiltonian += self.Delta * \
                        math.pow(d, -self.alpha) * (br * bext[s] +
                                                    Dagger(bext[s])*Dagger(br))
        return hamiltonian

    def setParameters(self, **kwargs):
        if "mu" in kwargs:
            self.mu = kwargs.get("mu")
            self.invalidateHamiltonian()
        if "t" in kwargs:
            self.t = kwargs.get("t")
            self.invalidateHamiltonian()
        if "Delta" in kwargs:
            self.Delta = kwargs.get("Delta")
            self.invalidateHamiltonian()
        if "alpha" in kwargs:
            self.alpha = kwargs.get("alpha")
            self.invalidateHamiltonian()

    def getSuffix(self):
        suffix = "_lat=" + str(self._lattice_length) + "x" + \
                 str(self._lattice_width) + "_periodic=" + str(self._periodic)\
                 + "_mu=" + str(self.mu) + "_t=" + str(self.t) + "_alpha=" + \
                 str(self.alpha) + "_Delta="+str(self.Delta)
        if self.n is not None:
            suffix += "_n="+str(self.n)
        if self.nmax is not None:
            suffix += "_nmax="+str(self.nmax)
        if self.nmin is not None:
            suffix += "_nmin="+str(self.nmin)
        if self.localNmax is not None:
            suffix += "_localnmax="+str(self.localNmax)
        if self._periodic:
            suffix += "_periodic=" + str(self._periodic)
        if self.window_length != self._lattice_length:
            suffix += "_window=" + str(self.window_length)
        suffix += "_level="+str(self._level)
        return suffix
