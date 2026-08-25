# The public Network Load Balancer and its restricted worker-node target rules
# are defined in network.tf because they share the VPC security boundary. The
# ingress controller NodePorts (30080/30443) are installed and validated in
# Task 11.4; GitHub Actions remains the application release owner.
