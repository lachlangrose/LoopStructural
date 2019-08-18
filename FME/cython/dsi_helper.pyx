import cython
import numpy as np
import numpy.linalg as la
cimport numpy as np
from math import *
@cython.boundscheck(False)
@cython.wraparound(False)
#cimport numpy.linalg as la
def cg(double [:,:,:] EG, long [:,:] neighbours, long [:,:] elements,double [:,:] nodes):
    cdef int Nc, Na, i,Ns, j, ne, ncons, e, n, neigh
    Nc = 5 #numer of constraints shared nodes + independent
    Na = 4 #number of nodes
    Ns = Na -1
    ne = len(neighbours)
    ncons = 0
    cdef int [:] flag = np.zeros(ne,dtype=np.int32)
    cdef double [:,:] c = np.zeros((len(neighbours)*4,Nc))
    cdef long [:,:] idc = np.zeros((ne*4,5),dtype=np.int64)
    cdef long [3] common 
    cdef double [:] norm = np.zeros((3))
    cdef double [:,:] shared_pts = np.zeros((3,3))
    cdef double [:] v1 = np.zeros(3)
    cdef double [:] v2 = np.zeros(3)
    cdef double [:,:] e1
    cdef double [:,:] e2
    cdef long [:] idl  = np.zeros(4,dtype=np.int64) 
    cdef long [:] idr = np.zeros(4,dtype=np.int64) 
    for e in range(ne):
        idl = elements[e,:]
        e1 = EG[e,:,:]
        flag[e] = 1
        for n in range(4):
            
            neigh = neighbours[e,n]
            idr = elements[neigh,:]
            if flag[neigh]== 1:
                continue
            if neigh == -1:
                continue
            e2 = EG[neigh,:,:]


            
            for i in range(Nc):
                idc[ncons,i] = -1

            i = 0
            for itr_right in range(Na):
                for itr_left in range(Na):
                    if idl[itr_left] == idr[itr_right]:
                        common[i] = idl[itr_left]
                        i+=1
            for j in range(3):
                for k in range(3):
                    shared_pts[j][k] = nodes[common[j]][k]#common
            for i in range(3):
                v1[i] = shared_pts[0,i] - shared_pts[1,i]
                v2[i] = shared_pts[2,i]-shared_pts[1,i]
            norm[0] = v2[2]*v1[1] - v1[2]*v2[1]
            norm[1] = v1[2]*v2[0] - v1[0]*v2[2]
            norm[2] = v1[0]*v2[1] - v1[1]*v2[0]#= np.cross(v1,v2)
            #norm[0] = v1[1]*v2[2]-v1[2]*v2[1]
            #norm[1] = v1[2]*v2[0]-v1[0]*v2[2]
            #norm[2] = v1[0]*v2[1] - v1[1]*v2[0]
            for itr_left in range(Na):
                idc[ncons,itr_left] = idl[itr_left]
                for i in range(3):
                    c[ncons,itr_left] += norm[i]*e1[i][itr_left]
            next_available_position = Na
            for itr_right in range(Na):
                common_index = -1
                for itr_left in range(Na):
                    if idc[ncons,itr_left] == idr[itr_right]:
                        common_index = itr_left

                position_to_write = 0
                if common_index != -1:
                    position_to_write = common_index
                else:
                    position_to_write = 4#next_available_position
                    next_available_position+=1
                idc[ncons,position_to_write] = idr[itr_right]
                for i in range(3):
                    c[ncons,position_to_write] -= norm[i]*e2[i][itr_right]
            ncons+=1
    return idc, c, ncons
def fold_cg(double [:,:,:] EG, double [:,:] X, long [:,:] neighbours, long [:,:] elements,double [:,:] nodes):
    cdef int Nc, Na, i,Ns, j, ne, ncons, e, n, neigh
    Nc = 5 #numer of constraints shared nodes + independent
    Na = 4 #number of nodes
    Ns = Na -1
    ne = len(neighbours)
    ncons = 0
    cdef int [:] flag = np.zeros(ne,dtype=np.int32)
    cdef double [:,:] c = np.zeros((len(neighbours)*4,Nc))
    cdef long [:,:] idc = np.zeros((ne*4,5),dtype=np.int64)
    cdef long [3] common 
    cdef double [:] norm = np.zeros((3))
    cdef double [:,:] shared_pts = np.zeros((3,3))
    cdef double [:] v1 = np.zeros(3)
    cdef double [:] v2 = np.zeros(3)
    cdef double [:,:] e1
    cdef double [:,:] e2
    cdef double [:] Xl
    cdef double [:] Xr

    cdef long [:] idl  = np.zeros(4,dtype=np.int64) 
    cdef long [:] idr = np.zeros(4,dtype=np.int64) 
    for e in range(ne):
        idl = elements[e,:]
        e1 = EG[e,:,:]
        flag[e] = 1
        Xl = X[e,:]
        for n in range(4):
            neigh = neighbours[e,n]
            idr = elements[neigh,:]
            if flag[neigh]== 1:
                continue
            if neigh == -1:
                continue
            e2 = EG[neigh,:,:]
            Xr = X[neigh,:]


            
            for i in range(Nc):
                idc[ncons,i] = -1

            i = 0
            for itr_left in range(Na):
                idc[ncons,itr_left] = idl[itr_left]
                for i in range(3):
                    c[ncons,itr_left] += Xl[i]*e1[i][itr_left]
            next_available_position = Na
            for itr_right in range(Na):
                common_index = -1
                for itr_left in range(Na):
                    if idc[ncons,itr_left] == idr[itr_right]:
                        common_index = itr_left
                position_to_write = 0
                if common_index != -1:
                    position_to_write = common_index
                else:
                    position_to_write = next_available_position
                    next_available_position+=1
                idc[ncons,position_to_write] = idr[itr_right]
                for i in range(3):
                    c[ncons,position_to_write] -= Xr[i]*e2[i][itr_right]
            ncons+=1
    return idc, c, ncons