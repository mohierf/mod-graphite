.. image:: https://api.travis-ci.org/mohierf/mod-graphite.svg?branch=develop
    :target: https://travis-ci.org/mohierf/mod-graphite
    :alt: Develop branch build status

.. image:: https://api.codacy.com/project/badge/Grade/4ffb2900db7949e98e528a4a9f342d71
    :target: https://www.codacy.com/manual/Shinken_modules/mod-graphite?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=mohierf/mod-graphite&amp;utm_campaign=Badge_Grade
    :alt: Development code static analysis

.. image:: https://codecov.io/gh/mohierf/mod-graphite/branch/develop/graph/badge.svg
    :target: https://codecov.io/gh/mohierf/mod-graphite
    :alt: Development code tests coverage


Graphite module
===============

Shinken module for exporting data to a Graphite server, version 2

This version is a refactoring of the previous graphite module which allows:

   - run as an external broker module
   - do not manage metrics until initial hosts/services status are received (avoid to miss prefixes)
   - remove pickle communication with Carbon (not very safe ...)
   - maintain a cache for the packets not sent because of connection problems
   - improve configuration features:
      - configure cache size
      - configure host check metric name
      - filter metrics warning and critical thresholds
      - filter metrics min and max values
      - filter service/metrics (avoid sending all metrics to Carbon)
      - manage host _GRAPHITE_PRE and service _GRAPHITE_POST to build metric id
      - manage host _GRAPHITE_GROUP as an extra hierarchy level for metrics (easier usage in metrics dashboard)

This new module improves some features but disabled some others:

   - this module is an external broker module.
   As of it the pickle interface between the module and Carbon is no more implemented

Installation
------------

   su - shinken

   shinken install graphite2

Configuration
-------------


   vi /etc/shinken/brokers/broker-master.cfg

   => modules graphite2

   vi /etc/shinken/modules/graphite2.cfg

   => host graphite


Run
---

   su -
   /etc/init.d/shinken restart


Hosts specific configuration
----------------------------
Use `_GRAPHITE_PRE` in the host configuration to set a prefix to use before the host name.
You can set `_GRAPHITE_PRE` in a global host template for all hosts.

For example, this prefix may be the API key of an hosted Graphite account (http://hostedgraphite.com).

Use `_GRAPHITE_GROUP` in the host configuration to set a prefix to use after the prefix and before the host name.
You can set `_GRAPHITE_GROUP` in a specific host template to allow easier filtering and organization in the metrics of a dashboard.

For example, declare this custom variable in an hostgroup or an host template.


Services specific configuration
-------------------------------
Use `_GRAPHITE_POST` in the service configuration to set a postfix to use after the service name.
