#Status Monitor

###Notes

1.) The architecture is a modified gossip protocol. 

-each node fires a status update to M random nodes every T seconds (user configurable; in this case M=8 and T=60)
-each node listens for incoming status updates and checks to see if it has received it before: if yes, it forwards that update to M random nodes, otherwise ignores
-each status update is timestamped with the node’s local time, thus receiving nodes can compare incoming updates to the last update (i.e. it is a logical timestamp)

2.) Nodes can join the service by simply sending a status update to a node

-node A that joins and sends a status update to node B will cause the addition of A to B’s list of known nodes (services are bootstrapped with a short list of known nodes)
-thus as a new node’s status gets forwarded to all nodes, that new node will begin receiving updates
-nodes will halt forwarding status updates to nodes that are down until until they come back online (thus leaving the service is a matter of halting the sending of status updates)

3.) A node is considered down if the last status update received was >T*4 seconds ago

-since a node is supposed to emit an update every T seconds, the likelihood of a node not receiving a sent status update in the last T*4 seconds is:

M/(N-1) = likelihood of being forwarded a status update S from another node (N = # participating nodes, M = # of nodes chosen for status forwarding)
1 - M/(N-1) = likelihood of not receiving a status update S from a single node
(1 - M/(N-1)) ^ (N-1) = likelihood of not receiving a status update S from ANY node
((1 - M/(N-1)) ^ (N-1)) ^ 4 = likelihood of not receiving a status update S from ANY node in the last T*4 seconds

Since N ~= 160 and M=8, the likelihood of node A not receiving a status update from node B’s (despite sending one) in the last T*4 secs is 5.5e-15 (i.e. this is the % inaccuracy). 

Note: this doesn’t consider dropped packets though the increase in % inaccuracy should not be material for this number of nodes. Since M=8 nodes are chosen at random to be sent a status update, even a 50% packet loss means that on average M*50% = 4 servers will receive it.

4.) Adding more status information is a matter of simply adding a member variable and unix command to the “Status” class (see: status_monitor.py) and updating the webpage

5.) Every participating node is capable of serving a status webpage

-the webpage displays the node’s list of last received status updates from each node:

1. Green: last status received <T*2 seconds ago 
2. Yellow: last status received between T*2 and T*4 seconds ago
3. Red: last status received >T*4 seconds ago
