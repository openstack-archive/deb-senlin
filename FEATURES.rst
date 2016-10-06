Senlin Feature Request Pipeline
===============================

This document records the feature requests the developer team has received and
considered. This document SHOULD NOT be treated as a replacement of the
blueprints (or specs) which already accompanied with a design.  The feature
requests here are meant to be a pipeline for mid-term goals that Senlin should
strive to achieve. Whenever a feature can be implemented with a practical
design, the feature should be moved to a blueprint (and/or specs) review.

This document SHOULD NOT be treated as a replacement of the `TODO` file the
development team is maintaining. The `TODO` file records actionable work items
that can be picked up by any developer who is willing to do it, while this
document records more general requirements that needs at least a draft design
before being worked on.


-------------
High Priority
-------------

Container Clustering
^^^^^^^^^^^^^^^^^^^^

[Austin Discussion: https://etherpad.openstack.org/p/newton-senlin-container]
We need to add a simple/generic container profile (which can be rebased on
some other projects later) so that we can experiment with issues unique to
container cluster management:

- Scheduling
- Networking/Storage
- APIs
- Security issues
- Dependencies


Event Listener
^^^^^^^^^^^^^^

To make Senlin responsive to events published by other OpenStack services, an
event subscriber is needed so that Senlin can receive notifications from
sources such as Ceilometer, Nova, or Zaqar.

This is of a high priority because Senlin needs it as one of its HA solutions.


Profile/Policy versioning support
^^^^^^^^^^^^^^^^^^^^^^

Profile/Policy schema could vary over time for properties being added or
deprecated. Versioning support is important for keeping backward
compatibility when profile/policy evolve.


Scavenger Process
^^^^^^^^^^^^^^^^^

Senlin needs a scavenger process that runs as a background daemon. It is
tasked with cleansing database for old data, e.g. event records. Its behavior
must be customizable because users may want the old records to be removed or
to be archived in a certain way.


Fault Tolerance
^^^^^^^^^^^^^^^

Senlin in most cases will be managing clusters with nodes distributed
somewhere. One problems inherent to such a distributed architecture is about
partial failures, communication latencies, concurrency, consistency etc. There
are hardware/software failures expected. Senlin must remain operational in the
face of such failures.


Access Permission Control
^^^^^^^^^^^^^^^^^^^^^^^^^

Currently, all access to Senlin objects like cluster, profile are project_safe
by default. This is for preventing user manipulating resources belong to other
users. However, sharing resource between different users/projects with limited
privilege(e.g. read-only, read-write) is also a very reasonable demand in many
cases. Therefore, we may need to provide access permission control in Senlin to
support this kind of requirement.


---------------
Middle Priority
---------------

Support Scheduled Actions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is a request to trigger some actions at a specified time. One typical use
case is to scale up a cluster before weekend or promotion season as a
preparation for the coming burst of workloads.


Blue-Green Deployment
^^^^^^^^^^^^^^^^^^^^^

Support to deploy environments using blue-green deployment pattern.
http://martinfowler.com/bliki/BlueGreenDeployment.html

Multi-cloud Support
^^^^^^^^^^^^^^^^^^^

In some case, user could have the demand to create/scale cluster cross different
clouds. Therefore, Senlin is supposed to have the ability to manage nodes which
span cross multiple clouds within the same cluster. Support from both profile
and policy layers are necessary for providing this ability.


User Defined Actions
^^^^^^^^^^^^^^^^^^^^

Actions in Senlin are mostly built-in ones at present. There are requirements
to incorporate Shell scripts and/or other structured software configuration
tools into the whole picture. One of the option is to provide a easy way for
Senlin to work with Ansible, for example.


Event Notification
^^^^^^^^^^^^^^^^^^

Event notification is a feature that enables an external tool to subscribe to
events sent from Senlin when interesting things happen. One option is to use
the messaging service provided by the Zaqar project.


Customizable Batch Processing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An important non-functional requirement for Senlin is the scale of clusters it
can handle. We will strive to make it handle large scale ones, however that
indicates that we need to improve DB accesses in case of heavy loads. One
potential tradeoff is to introduce an option for users to customize the size
of batches when large number of DB requests pouring in.


Container/Docker support
^^^^^^^^^^^^^^^^^^^^^^^^

Using Senlin to manage Container/Docker cluster is possible. We should
provide related support for users who have this requirement.



------------
Low Priority
------------

Define and Enforce Quotas
^^^^^^^^^^^^^^^^^^^^^^^^^

There is a potential request to limit how many clusters a user can create, how
large a cluster can become.


Use Barbican to Store Secrets
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Currently, Senlin uses the `cryptography` package for data encryption and
decryption. There should be support for users to store credentials using the
Barbican service, in addition to the current solution.


Use VPNaaS to Build Cross-Region/Cross-Cloud
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When building clusters that span more than one region or cloud, there are
requirements to place all cluster nodes on the same VPN so that workloads can
be distributed to the nodes as if they sit on the same network.


Vertical Scaling
^^^^^^^^^^^^^^^^

Though Senlin is mainly concerns about the horizontal scaling in/out support,
there are possibilities/requirements to scale nodes in the vertical direction.
Vertical scaling means automatically adding compute/storage/network resources
to cluster nodes. Depending on the support from corresponding services, this
could be explored.


Replace Green Threads with Python Threading
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Senlin is now using green threads (eventlets) for async executions. The
eventlets execution model is not making the use of multi-processing platforms
in an efficient way. Senlin needs a scalable execution engine, so native
multi-threading is needed.


Metrics Collection
^^^^^^^^^^^^^^^^^^

Senlin needs to support metric collections about the clusters and nodes it
manages. These metrics should be collectable by the ceilometer service, for
example.


AWS Compatible API
^^^^^^^^^^^^^^^^^^

There are requirements for Senlin to provide an AWS compatible API layer so
that existing workloads can be deployed to Senlin and AWS without needing to
change a lot of code or configurations.


Integration with Mistral
^^^^^^^^^^^^^^^^^^^^^^^^

There are cases where the (automated) operations on clusters and nodes form a
workflow. For example, an event triggers some actions to be executed in
sequence and those actions in turn triggers other actions to be executed.


Support to Suspend/Resume Operations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A user may want to suspend/resume a cluster or an individual node. Senlin
needs to provide a generic definition of 'suspend' and 'resume'. It needs to
be aware of whether the profile and the driver support such operations.


Interaction with Congress
^^^^^^^^^^^^^^^^^^^^^^^^^

This is of low priority because Senlin needs a notification mechanism in place
before it can talk to Congress. The reason to interact with Congress is that
there could be enterprise level policy enforcement that Senlin has to comply
to.


Investigation of Tooz
^^^^^^^^^^^^^^^^^^^^^

There is requirement to manage multiple senlin-engine instances in a
distributed way. Or, we can use a variant of DLM to manage cluster membership.
E.g. use redis/zookeeper to build clusters in their sense so that when the
cluster membership changes, we may possibly receive a notification. This would
be helpful for cluster health management.

Tooz is the promised focal point in this field, generalizing the many backends
that we don't want to care about. This TODO item is about two things:

#. Whether Tooz does provide a reliable membership management infra?
#. Is there a comparison between zookeeper and redis for example.


Run Senlin API under Apache
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Add support to have Senlin API run under Apache.


Baremetal Support
^^^^^^^^^^^^^^^^^

Managing baremetal cluster is a very common requirement from user. It is
reasonable for Senlin to support it by talking with service like Ironic.


TOSCA support
^^^^^^^^^^^^^

Provide TOSCA support in Senlin(maybe reuse heat-translator/tosca-parser?)


Dynamic Plugin Loading
^^^^^^^^^^^^^^^^^^^^^^

Design and implement dynamic plugin loading mechanism that allows loading
plugins from any paths.


Scaling to Existing Nodes
^^^^^^^^^^^^^^^^^^^^^^^^^

[Conclusion from Austin: https://etherpad.openstack.org/p/newton-senlin-as]

Senlin can improve scale-out operation so that it can add existing nodes to
a cluster when doing scale-out. We are not intended to scale to nodes not
created by Senlin.
