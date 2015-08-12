#!/usr/bin/env python
# -*- coding: utf-8 -*-
# July 17th / 2015


#from __future__ import division
from collections import defaultdict
from numpy import zeros, ones, log
import sys
import time
from multiprocessing import Process, Value, Array, Manager
from multiprocessing import Pool, RLock
import ctypes as ct
import numpy as np


null_emission_prob = 0.05
p0H = 0.4

smooth_factor = 0.2

def forward_with_t_scaled(a,pi,y,N,T,d, t_table, word_classes_dict): #N is the number of states and d is the target sentence
    # y is the source sentence
    # d is the dest sentence
    c_scaled = ones(T+1)
    alpha_hat = zeros((N+1,T+1))
    total_alpha_double_dot = 0
    for i in range(1,N+1):
        alpha_hat[(i,1)] = pi[i]*t_table[(y[0],d[i-1])]
        total_alpha_double_dot += alpha_hat[(i,1)]
    c_scaled[1] = 1.0/total_alpha_double_dot
    #alpha_hat[:,1] = c_scaled[1]*alpha_hat[:,1]
    for i in range(1,N+1):
        alpha_hat[(i,1)] = c_scaled[1]*alpha_hat[(i,1)]
    for t in range(1,T):
        total_alpha_double_dot = 0
        for j in range(1,N+1):
            total = 0
            for i in range(1,N+1):
                total += alpha_hat[(i,t)]*a[(i,j,word_classes_dict[d[i-1]], N)]
            alpha_hat[(j,t+1)] = t_table[(y[t],d[j-1])]*total
            total_alpha_double_dot += alpha_hat[(j,t+1)]
        c_scaled[t+1] = 1.0/total_alpha_double_dot
        for i in range(1,N+1):
            alpha_hat[(i,t+1)] = c_scaled[t+1]*alpha_hat[(i,t+1)]
        #alpha_hat[:,t+1] = c_scaled[t+1]*alpha_hat[:,t+1]

    return (alpha_hat,c_scaled)
def backward_with_t_scaled(a,pi,y,N,T,d, t_table,c_scaled, word_classes_dict):
    beta_hat = zeros((N+1,T+1))
    for i in range(1,N+1):
        beta_hat[(i,T)] = c_scaled[T]
    #beta_hat[:,T] = c_scaled[T]
    for t in range(T-1,0,-1):
        for i in range(1,N+1):
            total = 0
            for j in range(1,N+1):
                total += beta_hat[(j,t+1)]*a[(i,j,word_classes_dict[d[i-1]],N)]*t_table[(y[t],d[j-1])]
            beta_hat[(i,t)] = c_scaled[t]*total
    return beta_hat


def initializeUniformly(N, num_classes): # K is the number of all possible values for Ys
    twoN = 2*N;
    a = zeros((twoN+1,twoN+1,2*num_classes+2,N+1))      #This should be checked N+1 not 2N+1
    #manager = Manager()
    #a = dict()
    pi = zeros(twoN+1)
    for i in range(1,twoN+1):
        pi[i] = 1.0/twoN
    for i in range(1,twoN+1):
        for j in range(1,twoN+1):
            a[i,j,:,N] = 1.0/twoN
    return (a,pi)

def compute_c(): #Indirect HMM-based hypothesis alignment  by He et al.
    k = 2
    c = defaultdict(int)
    for d in range(-5,8):
        c[d] = 1.0/pow(1+abs(d-1),k)
    return c

def initializeBasedOnC(N):
    a = zeros((N+1,N+1))
    pi = zeros(N+1)

    c = compute_c()

    total = defaultdict(int)
    for i in range(1,N+1):
        pi[i] = 1.0/N
    for l in range(1,N+1):
        for i in range(1,N+1):
            total[i] += c[l-i]
    for i in range(1,N+1):
        for j in range(1,N+1):
            a[(i,j)] = c[j-i]/total[i]
#     for j in range(1,N+1):
#         for y_t in yValues:
#             b[(j,y_t)] = t[(y_t,)]
    return (a,pi)

def maxTargetSentenceLength(bitext):
    maxLength = 0
    target_length_map = dict()
    for (s,d) in bitext:
        if len(d) > maxLength:
            maxLength = len(d)
        if len(d) not in target_length_map:
            target_length_map[len(d)] = 1
    return (maxLength, target_length_map)

#   Smoothing transition probabilities, Och and Ney, 2000
#   (Here, we use smoothing equation but for the whole english sentence with length 2I to get right probabilities)
def smooth_transition_probabilities(a, I):
    for i in range(1, 2*I+1):
        for j in range(1,2*I+1):
            a[i][j][I] = smooth_factor*(0.5/I) + (1 - smooth_factor) * a[i][j][I]


def map_bitext_to_int(sd_count):
    #index = zeros(len(sd_count)) #index vector
    index = defaultdict(int)
    biword = defaultdict(int)
    for (i,(s,d)) in enumerate(sd_count):
        index[(s,d)] = i
        biword[i] = (s,d)
    return (index,biword)

def readClasses(fileName, num_classes, e_count):
    print "classes"
    word_classes_dict = dict()
    class_file = open(fileName, 'r')
    cnt = 0
    file_lines = []
    for line in class_file:
        print line
        file_lines += [line]
        colonIndex = int(line.index(':'))
        classIndex = int(line[:colonIndex ])

        word_list = line[colonIndex+1:].split(',')
        for w in word_list:
            word_classes_dict[w] = classIndex
        cnt += 1
        if cnt == num_classes:
            break

    list_of_comma_containing_words = []
    for word in e_count:
        if ',' in word:
            if (word == ','):
                list_of_comma_containing_words += [',,']
            else:
                list_of_comma_containing_words += [word]

    print 'ist ', list_of_comma_containing_words

    for line in file_lines:
        for word in list_of_comma_containing_words:
            if word in line:
                colonIndex = int(line.index(':'))
                classIndex = int(line[:colonIndex ])
                print 'word ', word, 'class ', classIndex
                word_classes_dict[word] = classIndex


    #Found from the classes file
    word_classes_dict[','] = word_classes_dict[',,']
    #word_classes_dict[','] = 5
    #word_classes_dict['$'] = 37
    #word_classes_dict['1,122,000'] = 22
    #word_classes_dict['25,000'] = 41
    #word_classes_dict['20,000'] = 42
    #word_classes_dict['2,958'] = 42
    #word_classes_dict['null'] = 1

    return word_classes_dict

        #word_classes_dict[]
def baumWelch(bitext_sd, s_count,t_table,sd_count, d_count):#L is the number of observations
    (N, target_length_map) = maxTargetSentenceLength(bitext_sd)
    print 'N',N
    N_max = N
    Y = bitext_sd

    yValues = s_count.keys()#computes all possible english words
    (indexMap,biword) = map_bitext_to_int(sd_count)
    sd_size = len(indexMap)
    lastLikelihood = 0
    #target length list is used for filtering out the re-estimation computation for the lengths that do not exist in the training data
    num_classes = 50
    file = '/cs/natlang-user/amansour/giza-pp/mkcls-v2/outClasses20k.cats'
    word_classes_dict = readClasses(file, num_classes, d_count)
    L = len(Y)

    for iterations in range(0,5):
        #E step
        #c = defaultdict(int)
        startTime = time.time()
        print 'iteration',iterations
        logLikelihood = 0
        totalGammaOverAllObservations = zeros(N+1)
        totalGammaDeltaOverAllObservations_t = zeros((N+1,sd_size))
        totalGammaDeltaOverAllObservations_t_overall_states = zeros(sd_size)
        totalGammaDeltaOverAllObservations_t_overall_states_over_dest = defaultdict(int)

        totalGamma1OverAllObservations = zeros(N+1)
        totalC_j_Minus_iOverAllObservations = zeros((N+1,N+1,num_classes+2,N+1))
        totalC_l_Minus_iOverAllObservations = zeros((N+1,num_classes+2,N+1))
        for (y,x) in Y: #y is the source sentence and x is the target sentence
            T = len(y)
            N = len(x)
            c = defaultdict(int)

            if iterations == 0:
                (a, pi) = initializeUniformly(N, num_classes)
            alpha_hat, c_scaled = forward_with_t_scaled(a, pi, y, N, T, x, t_table, word_classes_dict) #BE careful on indexing on x
            beta_hat = backward_with_t_scaled(a, pi, y, N, T, x, t_table, c_scaled, word_classes_dict) #else:

            #alpha_hat = forward_with_t(a, pi, y, N, T, x, t_table)
            #beta_hat = backward_with_t(a, pi, y, N, T, x, t_table)
	    #print alpha_hat
	    #print beta_hat
	    #print c_scaled
            gamma = zeros((N+1,T+1))
            xi = zeros((N+1,N+1,T+1))
            #gamma = (alpha_hat*beta_hat)/c_scaled
            #liklihood = 1.0/np.prod(c_scaled)
            for t in range(1,T):
                logLikelihood += -log(c_scaled[t])

                for i in range(1,N+1):
                    gamma[(i,t)] = (alpha_hat[(i,t)]*beta_hat[(i,t)])/c_scaled[t]
                    totalGammaOverAllObservations[i] += gamma[(i,t)]
                    totalGammaDeltaOverAllObservations_t[(i,indexMap[(y[t-1],x[i-1])])] += gamma[(i,t)]

            t = T
            logLikelihood += -log(c_scaled[t])
            #print 'likelihood ', liklihood, logLikelihood
            for i in range(1,N+1):
                gamma[(i,t)] = (alpha_hat[(i,t)]*beta_hat[(i,t)])/c_scaled[t]
                totalGammaOverAllObservations[i] += gamma[(i,t)]
                totalGammaDeltaOverAllObservations_t[(i,indexMap[(y[t-1],x[i-1])])] += gamma[(i,t)]
	    #print totalGammaOverAllObservations
            for t in range(1,T):
                for i in range(1,N+1):
                    C_e_i = word_classes_dict[x[i-1]]
                    for j in range(1,N+1):
                        xi[(i,j,t)] = (alpha_hat[(i,t)]*a[(i,j,C_e_i,N)]*t_table[(y[t],x[j-1])]*beta_hat[(j,t+1)])

            for i in range(1,N+1):
                totalGamma1OverAllObservations[i] += gamma[(i,1)]
            for d in range(-N - 1,N+1):
                #c[d] = 0
                for t in range(1,T):
                    for i in range(1,N+1):
                        if i+d <= N and i+d >= 1:
                            c[(d,word_classes_dict[x[i-1]])] += xi[(i,i+d,t)]

            #Liang et al. suggestion
#             for d in c:
#                 if d < -7:
#                     c[-7] += c[d]
#                     c[d] = 0
#                 if d > 7:
#                     c[7] += c[d]
#                     c[d] = 0


            for i in range(1,N+1):
                class_of_e_i = word_classes_dict[x[i-1]]
                for j in range(1,N+1):
#                     if j-i >= 7:
#                         totalC_j_Minus_iOverAllObservations[(i,j)] += c[7]
#                     elif j-i <= -7:
#                         totalC_j_Minus_iOverAllObservations[(i,j)] += c[-7]
#                     else:

                        totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i,N)] += c[(j-i, class_of_e_i)]
                        #if i == 24 and j == 21:
                        #    print class_of_e_i, 'this sample ' , totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i,N)]
                for l in range(1,N+1):
#                     if l-i >= 7:
#                         totalC_l_Minus_iOverAllObservations[i] += c[7]
#                     elif l-i <= -7:
#                         totalC_l_Minus_iOverAllObservations[i] += c[-7]
#                     else:
                        totalC_l_Minus_iOverAllObservations[(i, class_of_e_i, N)] += c[(l-i, class_of_e_i)]

	    #print totalC_j_Minus_iOverAllObservations
        print 'likelihood ', logLikelihood
        #lastLikelihood = liklihood
        N = len(totalGamma1OverAllObservations)-1
        #print N
        for i in range(1,N+1):
            for k in range(sd_size):
                totalGammaDeltaOverAllObservations_t_overall_states[k] += totalGammaDeltaOverAllObservations_t[(i,k)]
                (f,e) = biword[k]
                totalGammaDeltaOverAllObservations_t_overall_states_over_dest[e] += totalGammaDeltaOverAllObservations_t[(i,k)]
        totalGammaOverAllObservationsOverAllStates = 0.0
        for i in range(1,N+1):
            totalGammaOverAllObservationsOverAllStates += totalGammaOverAllObservations[i]

        #M Step
        #we can clear a, b and pi here and then set the values for them
        a = zeros((2*N+1,2*N+1,2*num_classes+2,N+1))
        #a = dict()
        pi = zeros(2*N+1)
        t_table = defaultdict(int)

        #print 'pi', pi
        twoN = 2*N
        for i in range(1,2*N+1):
            pi[i] = 1.0/twoN #totalGamma1OverAllObservations[i]*(1.0/L)

            '''for j in range(1,N+1):
                a[(i,j)] = totalC_j_Minus_iOverAllObservations[(i,j)]/totalC_l_Minus_iOverAllObservations[i]
            '''
        #a[(i,j,I)] = p(j|i,I)
        #for (i, j, I) in totalC_j_Minus_iOverAllObservations:
        for I in target_length_map:
            for i in range(1,I+1):
                for j in range(1,I+1):
                    for class_of_e_i in range(2,num_classes+2):
                        #if i == 24 and j == 21 and class_of_e_i == 27 :
                        #    print 'this sample in estimation ' , totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i,I)]
                        #print 'total C ', totalC_l_Minus_iOverAllObservations[i,class_of_e_i,I]
                        a[(i,j,class_of_e_i,I)] = (1-p0H)*totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i,I)]/totalC_l_Minus_iOverAllObservations[i,class_of_e_i,I]

        for I in target_length_map:
            for i in range(1,I+1):
                for C_e_i in range(2,num_classes+2):
                    a[i][i + I][C_e_i][I] = p0H
                    a[i + I][i + I][C_e_i+num_classes][I] = p0H     #We assume class of null is 1

        for I in target_length_map:
            for i in range(1,N+1):
                #C_e_i = word_classes_dict[]
                for j in range(1,N+1):
                    for C_e_i in range(2,num_classes+2):
                        a[i+I][j][C_e_i+num_classes][I] = a[i][j][C_e_i][I]     #We assume class of null is 1

         #************RUN IT ON TWON
        #normalize_table(a)
        #for I in target_length_map:
        #    smooth_transition_probabilities(a, I)

        '''for I in target_length_map:
            check_probability(a, I)
        '''
        for k in range(sd_size):
            (f,e) = biword[k]
            t_table[(f,e)] = totalGammaDeltaOverAllObservations_t_overall_states[k]/totalGammaDeltaOverAllObservations_t_overall_states_over_dest[e]
        endTime = time.time()
        print "run time for one iteration of hmm_with_length_with_array_null model %.2gs" % (endTime - startTime)
        print iterations
    print target_length_map
    return (a,t_table,pi, word_classes_dict)


def Expectation2(lock, t_table, N, Y, sd_size, indexMap, iterations, totalGammaOverAllObservations, totalGammaDeltaOverAllObservations_t, totalGamma1OverAllObservations, totalC_j_Minus_iOverAllObservations, totalC_l_Minus_iOverAllObservations,start,end,a, pi,logLikelihood, lastLogLikelihood, num_classes, word_classes_dict):
    #print 'Expectation2'
    for y, x in Y[start:end]: #y is the source sentence and x is the target sentence
        T = len(y)
        N = len(x)
        c = defaultdict(int)
        #print 'it', iterations
        if iterations == 0:
            (a, pi) = initializeUniformly(N, num_classes)
        alpha_hat, c_scaled = forward_with_t_scaled(a, pi, y, N, T, x, t_table, word_classes_dict) #BE careful on indexing on x
        beta_hat = backward_with_t_scaled(a, pi, y, N, T, x, t_table, c_scaled, word_classes_dict) #else:
        #    alpha = forward(a, b, pi, y, N, T)
        #    beta = backward(a, b, pi, y, N, T)

        gamma = np.zeros((N + 1, T + 1))
        xi = zeros((N + 1, N + 1, T + 1))

        for t in range(1, T):
            #print 'c_scaled ',c_scaled[t]
            with lock:
                logLikelihood.value += -(log(c_scaled[t]))
            for i in range(1, N + 1):
                gamma[(i,t)] = (alpha_hat[(i,t)]*beta_hat[(i,t)])/c_scaled[t]
                with lock:
                    totalGammaOverAllObservations[i] += gamma[i, t]
                address = (i * sd_size) + indexMap[(y[t - 1], x[i - 1])]
                with lock:
                    totalGammaDeltaOverAllObservations_t[address] += gamma[i, t]
        t = T
        with lock:
            logLikelihood.value += -(log(c_scaled[t]))
        for i in range(1, N + 1): #
            gamma[(i,t)] = (alpha_hat[(i,t)]*beta_hat[(i,t)])/c_scaled[t]
            with lock:
                totalGammaOverAllObservations[i] += gamma[i, t] #               totalGammaDeltaOverAllObservations[(i,y[t-1])] += gamma[(i,t)]
            #totalGammaDeltaOverAllObservations_t[(i,y[t-1],x[i-1])] += gamma[(i,t)]
            address = (i * sd_size) + indexMap[(y[t - 1], x[i - 1])]
            with lock:
                totalGammaDeltaOverAllObservations_t[address] += gamma[i, t]
        for t in range(1, T):
            for i in range(1, N + 1):
                C_e_i = word_classes_dict[x[i-1]]
                for j in range(1, N + 1):
#                        if iterations == 0:
                    xi[i, j, t] = alpha_hat[(i, t)] * a[(i, j, C_e_i, N)] * t_table[(y[t], x[j - 1])] * beta_hat[(j, t + 1)] #                        else:

#                            xi[(i,j,t)] = (alpha[(i,t)]*a[(i,j)]*b[(j,y[t])]*beta[(j,t+1)])/total[t]
#                        totalXiOverAllObservations[(i,j)] += xi[(i,j,t)]
        for i in range(1, N + 1):

            totalGamma1OverAllObservations[i] += gamma[i, 1]

        for d in range(-N - 1, N+1):
            #c[d] = 0
            for t in range(1, T):
                for i in range(1, N + 1):
                    if i + d <= N and i + d >= 1:
                        if (d >= 7 or d <= -7) :
                            for d_prime in range(-7,8):
                                c[(d_prime,word_classes_dict[x[i-1]])] += xi[(i,i+d,t)]/15.0
                        else:
                            c[(d,word_classes_dict[x[i-1]])] += xi[(i,i+d,t)]


        #print 'c',c
        #Liang et al. suggestion
#             for d in c:
#                 if d < -7:
#                     c[-7] += c[d]
#                     c[d] = 0
#                 if d > 7:
#                     c[7] += c[d]
#                     c[d] = 0
	#print 'totalC_j_Minus_iOverAllObservations',totalC_j_Minus_iOverAllObservations
        #print 'N',N
        for i in range(1, N + 1):
                class_of_e_i = word_classes_dict[x[i-1]]
                for j in range(1, N + 1): #                     if j-i >= 7:
    #                         totalC_j_Minus_iOverAllObservations[(i,j)] += c[7]
    #                     elif j-i <= -7:
    #                         totalC_j_Minus_iOverAllObservations[(i,j)] += c[-7]
    #                     else:


                    with lock:
                        if j-i >= 7 :
                            totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i, N)] += c[(7, class_of_e_i)]
                        elif j - i <= -7 :
                            totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i, N)] += c[(-7, class_of_e_i)]
                        else:
                            totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i, N)] += c[(j - i, class_of_e_i)]

                for l in range(1, N + 1): #                     if l-i >= 7:
#                         totalC_l_Minus_iOverAllObservations[i] += c[7]
#                     elif l-i <= -7:
#                         totalC_l_Minus_iOverAllObservations[i] += c[-7]
#                     else:
                    with lock:
                        if l-i >= 7:
                            totalC_l_Minus_iOverAllObservations[(i, class_of_e_i,N)] += c[(7, class_of_e_i)]
                        elif l - i <= -7 :
                            totalC_l_Minus_iOverAllObservations[(i, class_of_e_i,N)] += c[(-7, class_of_e_i)]
                        else:
                            totalC_l_Minus_iOverAllObservations[(i, class_of_e_i,N)] += c[(l - i, class_of_e_i)]



    #return N, i, a, pi, j


def baumWelchP(bitext_sd, s_count,t_table,sd_count, d_count):#L is the number of observations

    print 'null prob ', null_emission_prob, ' and p0H ', p0H
    (N, target_length_map) = maxTargetSentenceLength(bitext_sd)
    print 'N',N
    N_max = N
    Y = bitext_sd

    yValues = s_count.keys()#computes all possible english words
    (indexMap,biword) = map_bitext_to_int(sd_count)
    sd_size = len(indexMap)
    num_classes = 50
    file = '/cs/natlang-user/amansour/giza-pp/mkcls-v2/outClasses20k.cats'
    word_classes_dict = readClasses(file, num_classes, d_count)
    lastLikelihood = 0

    twoN = 2*N
    #a = zeros((N+1,N+1))

    a_array = Array(ct.c_double,((twoN+1)*(twoN+1)*(2*num_classes+2)*(N+1)))
    a_array2 = np.frombuffer(a_array.get_obj()) # mp_arr and arr share the same memory
    a = a_array2.reshape((twoN+1,twoN+1,(2*num_classes+2),N+1)) # b and arr share the same memory

    '''
    manager = Manager()
    a = manager.dict()
    '''
    #pi = zeros(N+1)
    pi = Array('d', twoN+1)

    logLikelihood = Value('d',0.0)

    lastLogLikelihood = Value('d',0.0)

    L = len(Y)
    #N = len(Y[0][1]) #first sentence x length
    #(a,pi) = initializeUniformly(N)


    for iterations in range(0,5):
        #E step
        #c = defaultdict(int)
        startTime = time.time()
        print 'iteration',iterations
        logLikelihood.value = 0.0
        #totalGammaOverAllObservations = zeros(N+1)
        totalGammaOverAllObservations = Array('d', [0]*(N+1))

        #totalGammaDeltaOverAllObservations_t = zeros((N+1,sd_size))
        totalGammaDeltaOverAllObservations_t = Array('d',[0]*((N+1)*(sd_size)))

        #totalGammaDeltaOverAllObservations_t_overall_states = zeros(sd_size)
        totalGammaDeltaOverAllObservations_t_overall_states = Array('d',[0]*sd_size)

        totalGammaDeltaOverAllObservations_t_overall_states_over_dest = defaultdict(int)


        #totalGamma1OverAllObservations = zeros(N+1)
        totalGamma1OverAllObservations = Array('d',[0]*(N+1))

        #totalC_j_Minus_iOverAllObservations = zeros((N+1,N+1))


        totalC_j_Minus_iOverAllObservations_array = Array(ct.c_double,(N+1)*(N+1)*(num_classes+2)*(N+1))
        totalC_j_Minus_iOverAllObservations_array2 = np.frombuffer(totalC_j_Minus_iOverAllObservations_array.get_obj())
        totalC_j_Minus_iOverAllObservations = totalC_j_Minus_iOverAllObservations_array2.reshape((N+1,N+1,num_classes+2,N+1))
        for i in range(N+1):
            for j in range(N+1):
                for k in range(N+1):
                    for C_e_i in range(2, num_classes+2):
                        totalC_j_Minus_iOverAllObservations[i,j, C_e_i, k] = 0.0
        '''
        manager = Manager()

        totalC_j_Minus_iOverAllObservations = manager.dict()
        '''
        #totalC_l_Minus_iOverAllObservations = zeros(N+1)

        '''
        totalC_l_Minus_iOverAllObservations = Array('d',[0]*(N+1))
        '''
        totalC_l_Minus_iOverAllObservations_array = Array(ct.c_double,(N+1)*(num_classes+2)*(N+1))
        totalC_l_Minus_iOverAllObservations_array2 = np.frombuffer(totalC_l_Minus_iOverAllObservations_array.get_obj())
        totalC_l_Minus_iOverAllObservations = totalC_l_Minus_iOverAllObservations_array2.reshape((N+1,(num_classes+2),N+1))
        for i in range(N+1):
            for j in range(N+1):
                for C_e_i in range(2, num_classes+2):
                    totalC_l_Minus_iOverAllObservations[(i,C_e_i,j)] = 0.0
        '''
        manager2 = Manager()
        totalC_l_Minus_iOverAllObservations = manager2.dict()
        '''
        intervals = 10
        jobs = []
        lock = RLock()
        length_of_interval = L/intervals
        for i in range(0,intervals-1):
            start = i*length_of_interval
            end = (i+1)*length_of_interval
            #print start
            #print end
            p = Process(target=Expectation2, args = (lock, t_table, N, Y, sd_size, indexMap, iterations, totalGammaOverAllObservations, totalGammaDeltaOverAllObservations_t, totalGamma1OverAllObservations, totalC_j_Minus_iOverAllObservations, totalC_l_Minus_iOverAllObservations,start,end,a, pi,logLikelihood, lastLogLikelihood, num_classes, word_classes_dict))
            p.start()
            jobs.append(p)

        start = (intervals-1)*length_of_interval
        end = L
        p = Process(target=Expectation2, args = (lock, t_table, N, Y, sd_size, indexMap, iterations, totalGammaOverAllObservations, totalGammaDeltaOverAllObservations_t, totalGamma1OverAllObservations, totalC_j_Minus_iOverAllObservations, totalC_l_Minus_iOverAllObservations,start,end,a, pi,logLikelihood, lastLogLikelihood, num_classes, word_classes_dict))
        p.start()
        jobs.append(p)
        for p in jobs:
            p.join()


        endTime = time.time()

        #print N
        print "%.2gs" % (endTime - startTime)
        #N = len(totalGamma1OverAllObservations)-1
        #print N
        print 'last , new ', lastLogLikelihood.value, logLikelihood.value
        #print 'likelihood difference ', (logLikelihood.value - lastLogLikelihood.value)
        lastLogLikelihood.value = logLikelihood.value

        totalGammaOverAllObservationsOverAllStates = 0.0
        sartTime = time.time()
        for i in range(1,N+1):
            totalGammaOverAllObservationsOverAllStates += totalGammaOverAllObservations[i]




        print 'likelihood ', logLikelihood
        #lastLikelihood = liklihood
        N = len(totalGamma1OverAllObservations)-1
        #print N

        # Create expected_counts(d,c) to be consistent with the Berg-Kirkpatrick et al.
        # To make it more memory efficient just keep either totalGammaDeltaOverAllObservations_t_overall_states or expected_counts
        expected_counts = defaultdict(int)

        for i in range(1,N+1):
            for k in range(sd_size):

                address = i*sd_size + k
                totalGammaDeltaOverAllObservations_t_overall_states[k] += totalGammaDeltaOverAllObservations_t[address]
                (f,e) = biword[k]
                totalGammaDeltaOverAllObservations_t_overall_states_over_dest[e] += totalGammaDeltaOverAllObservations_t[address]


        for k in range(sd_size):
            (f, e) = biword[k]
            expected_counts[(f, e)] = totalGammaDeltaOverAllObservations_t_overall_states[k]

        totalGammaOverAllObservationsOverAllStates = 0.0
        for i in range(1,N+1):
            totalGammaOverAllObservationsOverAllStates += totalGammaOverAllObservations[i]

        # M Step
        # We can clear a, b and pi here and then set the values for them
        a = zeros((2*N+1,2*N+1,(2*num_classes+2),N+1))

        pi = zeros(2*N+1)
        t_table = defaultdict(int)

        twoN = 2*N
        for i in range(1,2*N+1):
            pi[i] = 1.0/twoN #totalGamma1OverAllObservations[i]*(1.0/L)

            '''for j in range(1,N+1):
                a[(i,j)] = totalC_j_Minus_iOverAllObservations[(i,j)]/totalC_l_Minus_iOverAllObservations[i]
            '''
        #a[(i,j,I)] = p(j|i,I)
        #for (i, j, I) in totalC_j_Minus_iOverAllObservations:
        for I in target_length_map:
            for i in range(1,I+1):
                for j in range(1,I+1):
                    for class_of_e_i in range(2,num_classes+2):
                        #if i == 24 and j == 21 and class_of_e_i == 27 :
                        #    print 'this sample in estimation ' , totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i,I)]
                        #print 'total C ', totalC_l_Minus_iOverAllObservations[i,class_of_e_i,I]
                        a[(i,j,class_of_e_i,I)] = (1-p0H)*totalC_j_Minus_iOverAllObservations[(i,j,class_of_e_i,I)]/totalC_l_Minus_iOverAllObservations[i,class_of_e_i,I]

        '''for I in target_length_map:
            for i in range(1,I+1):
                for C_e_i in range(2,num_classes+2):
                    a[i][i + I][C_e_i][I] = p0H
                    a[i + I][i + I][C_e_i+num_classes][I] = p0H     #We assume class of null is 1
        '''
        '''for I in target_length_map:
            for i in range(1,N+1):
                for j in range(1,N+1):
                    for C_e_i in range(2,num_classes+2):
                        a[i+I][j][C_e_i+num_classes][I] = a[i][j][C_e_i][I]     #We assume class of null is 1
        '''
        #************RUN IT ON TWON
        #normalize_table(a)

        
	#for I in target_length_map:
        #    smooth_transition_probabilities(a, I)
	
        '''for I in target_length_map:
            check_probability(a, I)
        '''


        #print 'a ', a
        #check_probability(a, N)
        for k in range(sd_size):
            (f,e) = biword[k]
            t_table[(f,e)] = totalGammaDeltaOverAllObservations_t_overall_states[k]/totalGammaDeltaOverAllObservations_t_overall_states_over_dest[e]
        endTime = time.time()
        print "run time for one iteration of hmm_with_length_with_array_null parallel model %.2gs" % (endTime - startTime)

        print iterations

    return (a,t_table,pi, word_classes_dict)

def check_probability(p, N):
    for i in range(1,2*N+1):
        total = 0
        for j in range(2*N+1):
            total += p[i][j][N]
        if total != 1 :
            print "not probability ",i, ' ', j, ' ', total
        else:
            print "YEEEESSSS ", total

def log_viterbi(a,t_table,pi,N,o,d, word_classes_dict,num_classes):
    V = zeros((2*N+1,len(o)))
    ptr = zeros((2*N+1,len(o)))
    new_d = []

    for i in range(len(d)):
        new_d.append(d[i])
    for i in range(len(d), 2*len(d)):
        new_d.append('null')


    #print 'french sentence ', o, ' english sentence ', d, ' new english ', newd, ' pi ', pi
    #print 'N', N, ' ', len(newd)
    for q in range(1,2*N+1):
        if (o[0],new_d[q-1]) in t_table:
            if t_table[(o[0],new_d[q-1])] == 0 or pi[q] == 0:
                V[(q,0)] = -sys.maxint
            else:
                V[(q,0)] = log(t_table[(o[0],new_d[q-1])])#log(pi[q])+log(t_table[(o[0],newd[q-1])])
        else:
            #
            if new_d[q-1] == 'null' :
                #print 'q ', q, ' ', pi[q], ' ', null_emission_prob
                V[(q,0)] = log(null_emission_prob)#log(pi[q])+log(null_emission_prob)
            else:
                V[(q,0)] = 0
    for t in xrange(1,len(o)):
        for q in range(1,2*N+1):
            maximum = -sys.maxint
            max_q = -sys.maxint

            for q_prime in range(1,2*N+1):

                #if newd[q_prime-1] == 'null':
                #    C_d_q_prime = word_classes_dict[newd[q_prime-1-N]]
                    #if newd[q-1] == 'null':
                    #    C_d_q_prime = C_d_q_prime + num_classes
                #else:
                #    C_d_q_prime = word_classes_dict[newd[q_prime-1]]

                if new_d[q-1] != 'null' and new_d[q_prime-1] != 'null':
                    C_d_q_prime = word_classes_dict[new_d[q_prime-1]]
                    if (o[t],new_d[q-1]) in t_table:
                        if a[(q_prime,q,C_d_q_prime,N)] != 0 and t_table[(o[t],new_d[q-1])] != 0 :
                            if V[(q_prime,t-1)]+log(a[(q_prime,q,C_d_q_prime,N)])+log(t_table[(o[t],new_d[q-1])]) > maximum :
                                maximum = V[(q_prime,t-1)]+log(a[(q_prime,q,C_d_q_prime,N)])+log(t_table[(o[t],new_d[q-1])])
                                max_q = q_prime
                elif new_d[q-1] == 'null' and new_d[q_prime-1] != 'null':
                    #C_d_q_prime = word_classes_dict[newd[q_prime-1]]
                    if V[(q_prime,t-1)]+log(p0H)+log(null_emission_prob) > maximum :
                            maximum = V[(q_prime,t-1)]+log(p0H)+log(null_emission_prob)
                            max_q = q_prime
                elif new_d[q-1] == 'null' and new_d[q_prime-1] == 'null':
                    if V[(q_prime,t-1)]+log(p0H)+log(null_emission_prob) > maximum :
                            maximum = V[(q_prime,t-1)]+log(p0H)+log(null_emission_prob)
                            max_q = q_prime
                elif new_d[q-1] != 'null' and new_d[q_prime-1] == 'null':
                    C_d_q_prime = word_classes_dict[new_d[q_prime-1-N]]
                    if a[(q_prime,q,C_d_q_prime,N)] != 0 :
                        if V[(q_prime,t-1)]+log(a[(q_prime,q,C_d_q_prime,N)])+log(t_table[(o[t],new_d[q-1])]) > maximum :
                            maximum = V[(q_prime,t-1)]+log(a[(q_prime,q,C_d_q_prime,N)])+log(t_table[(o[t],new_d[q-1])])
                            max_q = q_prime

            V[q,t] = maximum
            ptr[q,t] = max_q
    max_of_V = -sys.maxint
    q_of_max_of_V = 0
    for q in range(1,2*N+1):
        if V[(q,len(o)-1)] > max_of_V:
            max_of_V = V[(q,len(o)-1)]
            q_of_max_of_V = q
    trace = [q_of_max_of_V]

    q = q_of_max_of_V
    i = len(o)-1

    while i > 0:
        q = ptr[(q,i)]
        trace.insert(0, q)
        i = i -1
    return trace

def findBestAlignmentsForAll(bitext,a,t_table,pi):
    for (n,(S,D)) in enumerate(bitext):

        N = len(D)
        bestAlignment = log_viterbi(a, t_table, pi, N, S, D)
        for (i,a_i) in enumerate(bestAlignment):
            sys.stdout.write("%i-%i " % (i,a_i-1))
        sys.stdout.write("\n")


def findBestAlignmentsForAll_AER(bitext,a,t_table,pi,num_lines,alignmentFile, word_classes_dict, num_classes):
    alignment = open(alignmentFile,'w')
    #print 'alignment file ', alignmentFile
    for (n,(S,D)) in enumerate(bitext):
        N = len(D)

        bestAlignment = log_viterbi(a, t_table, pi, N, S, D, word_classes_dict, num_classes)
        for (i,a_i) in enumerate(bestAlignment):
            #CHANGE for null
            if a_i <= N:
                alignment.write("%i-%i " % (i+1,a_i))
	    #sys.stdout.write("%i-%i " % (i+1,a_i))
        alignment.write("\n")
	#sys.stdout.write('\n')
	if n == num_lines-1 :
		alignment.close()
		return

def findBestAlignmentsForAllWithIntersection_DS(bitext,a,b,pi,a_ds,b_ds,pi_ds):
    for (S,D) in bitext:
        #set1 = set()
        set2 = set()
        N = len(D)
        N_ds = len(S)
        #bestAlignment = log_viterbi(a, b, pi, N, S, D)
        bestAlignment_ds = log_viterbi(a_ds, b_ds, pi_ds, N_ds, D, S)
        #for (i,a_i) in enumerate(bestAlignment):
        #    set1.add((i,a_i-1))
        for (i,a_i) in enumerate(bestAlignment_ds):
            set2.add((a_i-1,i))
        #intersect = set1.intersection(set2)
        for (i_s,a_s) in set2:
            sys.stdout.write("%i-%i " % (i_s,a_s))
        sys.stdout.write("\n")

def findBestAlignmentsForAllWithIntersection(bitext,a,b,pi,a_ds,b_ds,pi_ds):
    for (S,D) in bitext:
        set1 = set()
        set2 = set()
        N = len(D)
        N_ds = len(S)
        bestAlignment = log_viterbi(a, b, pi, N, S, D)
        bestAlignment_ds = log_viterbi(a_ds, b_ds, pi_ds, N_ds, D, S)
        for (i,a_i) in enumerate(bestAlignment):
            set1.add((i,a_i-1))
        for (i,a_i) in enumerate(bestAlignment_ds):
            set2.add((a_i-1,i))
        intersect = set1.intersection(set2)
        for (i_s,a_s) in intersect:
            sys.stdout.write("%i-%i " % (i_s,a_s))
        sys.stdout.write("\n")
def findBestAlignmentsForAllWithIntersection_AER(bitext,a,b,pi,a_ds,b_ds,pi_ds,num_lines,alignmentFile):
    alignment = open(alignmentFile,'w')
    for (n,(S,D)) in enumerate(bitext):
        set1 = set()
        set2 = set()
        N = len(D)
        N_ds = len(S)
        bestAlignment = log_viterbi(a, b, pi, N, S, D)
        bestAlignment_ds = log_viterbi(a_ds, b_ds, pi_ds, N_ds, D, S)
        for (i,a_i) in enumerate(bestAlignment):
            set1.add((i,a_i-1))
        for (i,a_i) in enumerate(bestAlignment_ds):
            set2.add((a_i-1,i))
        intersect = set1.intersection(set2)
        for (i_s,a_s) in intersect:
	    alignment.write("%i-%i " % (i_s+1,a_s+1))
            #sys.stdout.write("%i-%i " % (i_s,a_s))
        alignment.write('\n')
	if n == (num_lines - 1) :
		return
	#sys.stdout.write("\n")



if __name__ == '__main__':
    file = '/cs/natlang-user/amansour/giza-pp/mkcls-v2/outClasses.cats'
    word_classes_dict = readClasses(file, 50)
    print 'class of need is : ', word_classes_dict['airline']
