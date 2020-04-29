""""Algorithms for shortest paths calculations."""
# !/usr/bin/python -tt
# -*- coding: utf-8 -*-
# =============================================================================
# File      : shortest_paths.py -- Module to calculate shortest paths and diameter
# Author    : Ingo Scholtes <scholtes@uni-wuppertal.de>
# Time-stamp: <Sun 2020-04-19 07:38 juergen>
#
# Copyright (c) 2016-2020 Pathpy Developers
# =============================================================================
from __future__ import annotations
from typing import TYPE_CHECKING, Any, List, Dict, Tuple, Optional, Union
from collections import defaultdict
import numpy as np
from scipy.sparse import csgraph  # pylint: disable=import-error
from queue import PriorityQueue

from pathpy import logger, tqdm

from ..core import network as net

# pseudo load class for type checking
if TYPE_CHECKING:
    from pathpy.core.network import Network
    from pathpy.core.node import Node

# from pathpy.core.path import Path

# create logger
LOG = logger(__name__)


def distance_matrix(network: Network,
                    weight: Union[str, bool, None] = None) -> np.ndarray:
    """Calculates shortest path distances between all pairs of nodes

    .. note::

        Shortest paths are calculated using the implementation 
        of the Floyd-Warshall algorithm provided in `scipy.csgraph`.

    Parameters
    ----------
    network : Network

        The :py:class:`Network` object that contains the network

    weighted : bool

        If True cheapest paths will be calculated.

    Examples
    --------
    Generate a path and add it to the network.

    >>> import pathpy as pp
    >>> net = pp.Network()
    >>> net.add_edges(('a', 'x'), ('x', 'y'), ('y', 'c'))
    >>> m = pp.algorithms.shortest_paths.distance_matrix(net)
    >>> m[0,3]
    3

    Add shorter path

    >>> net.add_edges(('a', 'x'), ('x', 'c'))
    >>> m = pp.algorithms.shortest_paths.distance_matrix(net)
    >>> m[0,3]
    2
    """

    A = network.adjacency_matrix(weight=weight)
    dist_matrix = csgraph.floyd_warshall(
        A, network.directed, unweighted=(not weight), overwrite=False)

    return dist_matrix


def all_shortest_paths(network: Network,
                       weight: Union[str, bool, None] = None,
                       return_distance_matrix: bool = True) -> Union[defaultdict, (defaultdict, np.ndarray)]:
    """Calculates shortest paths between all pairs of nodes.

    .. note::

        Shortest paths are calculated using a custom implementation of
        the Floyd-Warshall algorithm.

    Parameters
    ----------
    network : Network

        The :py:class:`Network` object that contains the network

    weighted : bool

        If True cheapest paths will be calculated.

    Examples
    --------
    Generate a path and add it to the network.

    >>> import pathpy as pp
    >>> net = pp.Network()
    >>> net.add_edges(('a', 'x'), ('x', 'c'))
    >>> paths = pp.algorithms.shortest_paths.all_shortest_paths(net)
    >>> paths['a']['c']
    {('a', 'x', 'c')}

    Add additional path

    >>> net.add_edges(('a', 'y'), ('y', 'c'))
    >>> paths = pp.algorithms.shortest_paths.all_shortest_paths(net)
    >>> paths['a']['c']
    {('a', 'x', 'c'), ('a', 'y', 'c')}

    """

    dist: defaultdict = defaultdict(lambda: defaultdict(lambda: np.inf))
    s_p: defaultdict = defaultdict(lambda: defaultdict(set))

    for e in network.edges:
        # set distances between neighbors to 1
        dist[e.v.uid][e.w.uid] = 1
        s_p[e.v.uid][e.w.uid].add((e.v.uid, e.w.uid))
        if not network.directed:
            dist[e.w.uid][e.v.uid] = 1
            s_p[e.w.uid][e.v.uid].add((e.w.uid, e.v.uid))

    for k in tqdm(network.nodes.keys(), desc='calculating shortest paths between all nodes'):
        for v in network.nodes.keys():
            for w in network.nodes.keys():
                if v != w:
                    if dist[v][w] > dist[v][k] + dist[k][w]:
                        # we have found a shorter path
                        dist[v][w] = dist[v][k] + dist[k][w]
                        s_p[v][w] = set()
                        for p in list(s_p[v][k]):
                            for q in list(s_p[k][w]):
                                s_p[v][w].add(p + q[1:])
                    elif dist[v][w] == dist[v][k] + dist[k][w]:
                        # we have found another shortest path
                        for p in list(s_p[v][k]):
                            for q in list(s_p[k][w]):
                                s_p[v][w].add(p + q[1:])

    for v in network.nodes.keys():
        dist[v][v] = 0
        s_p[v][v].add((v,))

    if return_distance_matrix:
        dist_arr = np.ndarray(shape=(network.number_of_nodes(), network.number_of_nodes()))
        for v in network.nodes:
            for w in network.nodes:
                dist_arr[network.nodes.index[v.uid], network.nodes.index[w.uid]] = dist[v.uid][w.uid]
        return s_p, dist_arr
    else :
        return s_p


def single_source_shortest_paths(network: Network, source: str) -> Union[dict, np.array]:
    """Calculates all shortest paths from a single given source node using a 
    custom implementation of Dijkstra's algorithm based on a priority queue.
    """
    Q: dict = dict()
    dist = dict()
    prev = dict()
    dist[source] = 0

    for v in network.nodes.uids:
        if v != source:
            dist[v] = np.inf
            prev[v] = None
        Q[v] = dist[v]

    while Q:
        u = min(Q.keys(), key=(lambda k: Q[k])) # TODO: Do this more efficiently with a proper priority queue
        del Q[u]
        for v in network.successors[u]:
            if dist[u] + 1 < dist[v.uid]:                
                dist[v.uid] = dist[u] + 1
                prev[v.uid] = u
                if v.uid in Q:
                    Q[v.uid] = dist[u] + 1
    
    # calculate distance vector
    dist_arr = np.zeros(network.number_of_nodes())
    for v in network.nodes:
        dist_arr[network.nodes.index[v.uid]] = dist[v.uid]

    # construct shortest paths 
    s_p: dict = dict()
    for dest in network.nodes:
        if dest.uid != source:
            path = [dest.uid]
            x = dest.uid
            while x != source and x != None:
                x = prev[x]
                path.append(x)
            if x == None:
                s_p[dest.uid] = None
            else:
                path.reverse()
                s_p[dest.uid] = tuple(path)
    return dist_arr, s_p


def shortest_path_tree(network: Network, source) -> Network:
    """Computes a shortest path tree rooted at the node with the
    given source uid."""

    n_tree = net.Network(directed = True)

    Q: dict = dict()
    dist = dict()
    prev = dict()
    dist[source] = 0

    for v in network.nodes.uids:
        if v != source:
            dist[v] = np.inf
            prev[v] = None
        Q[v] = dist[v]

    while Q:
        u = min(Q.keys(), key=(lambda k: Q[k])) # TODO: Do this more efficiently with a proper priority queue
        del Q[u]
        for v in network.successors[u]:
            if dist[u] + 1 < dist[v.uid]:                
                dist[v.uid] = dist[u] + 1
                prev[v.uid] = u
                if v.uid in Q:
                    Q[v.uid] = dist[u] + 1

    for k, v in prev.items():
        if v != None:
            n_tree.add_edge(v, k)

    return n_tree


def diameter(network: Network,
             weight: Union[str, bool, None] = None) -> float:
    """Calculates the length of the longest shortest path

    .. note::

        Shortest path lengths are calculated using the implementation
        of the Floyd-Warshall algorithm in scipy.csgraph.

    Parameters
    ----------
    network : Network

        The :py:class:`Network` object that contains the network

    weighted : bool

        If True cheapest paths will be calculated.

    Examples
    --------
    Generate simple network

    >>> import pathpy as pp
    >>> net = pp.Network(directed=False)
    >>> net.add_edge('a', 'x')
    >>> net.add_edge('x', 'c')
    >>> pp.algorithms.shortest_paths.diameter(net)
    2

    Add additional path

    >>> net.add_edge('a', 'c')
    >>> pp.algorithms.shortest_paths.diameter(net)
    1
    """
    return np.max(distance_matrix(network, weight=weight))


def avg_path_length(network: Network,
                    weight: Union[str, bool, None] = None) -> float:
    """Calculates the average shortest path length

    .. note::

        Shortest path lengths are calculated using the implementation
        of the Floyd-Warshall algorithm in scipy.csgraph.

    Parameters
    ----------
    network : Network

        The :py:class:`Network` object that contains the network

    weighted : bool

        If True cheapest paths will be calculated.

    Examples
    --------
    Generate simple network

    >>> import pathpy as pp
    >>> net = pp.Network(directed=False)
    >>> net.add_edge('a', 'x')
    >>> net.add_edge('x', 'c')
    >>> pp.algorithms.shortest_paths.avg_path_length(net)
    0.6667 # TODO is this correct or shoudl it be 0.888888?
    """
    return np.mean(distance_matrix(network, weight=weight))
