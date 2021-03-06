import numpy as np
from polynomialTrjNonlinear.Optimizer_nonlinear import PolynomialOptNonlinear
import yaml
from basic_functions import *
import rospy
from rotors_gazebo.msg import Float64Stamped


class PayloadDistributor(object):
    def __init__(self, mav_name, c_initial):
        self.mav_name = mav_name
        self.g = 9.81
        # for the payload
        self.mass_payload = 1.0
        self.H0_ = np.zeros((6, 6))
        self.J_payload = np.zeros((3, 3))
        # for the quad-rotors
        self.arm_length = 0.0
        self.mass_quad = 0.0
        self.num_agents = 4
        self.num_edges = 4
        self.relative_pos = np.zeros((3, self.num_agents))
        self.c0 = 0.0
        self.c1 = 0.0
        self.c2 = 0.0
        self.c3 = 0.0
        self.c = c_initial
        self.Sigma = np.zeros((3, 3))
        self.E_ = [np.zeros((6, 6)) for _ in range(self.num_agents)]
        self.E_inv = [np.zeros((6, 6)) for _ in range(self.num_agents)]
        self.c_E = [np.zeros((6, 6)) for _ in range(self.num_agents)]
        self.M0_ = [np.zeros((6, 6)) for _ in range(self.num_agents)]
        self.G0_ = np.zeros((6, 1))
        self.W0_ = [np.zeros((6, 1)) for _ in range(self.num_agents)]

        self.pre_processing()
        self.H0_[0:3, 0:3] = self.mass_payload * np.eye(3)
        self.H0_[3:, 3:] = self.J_payload
        self.G0_[2, 0] = self.g
        self.calculateMatrixE()
        self.planner = PolynomialOptNonlinear(N=10, dimension=3)

        # a matrix-centralized way:
        # self.consensor = ConsensusNet(self.num_agents, self.num_edges)

        # a ros-topic, pseudo-centralized way:
        topic_name_0 = '/' + self.mav_name + '_0' + '/' + 'c'
        topic_name_1 = '/' + self.mav_name + '_1' + '/' + 'c'
        topic_name_2 = '/' + self.mav_name + '_2' + '/' + 'c'
        topic_name_3 = '/' + self.mav_name + '_3' + '/' + 'c'

        self.sub_c0 = rospy.Subscriber(topic_name_0, Float64Stamped, self.cb_c0)
        self.sub_c1 = rospy.Subscriber(topic_name_1, Float64Stamped, self.cb_c1)
        self.sub_c2 = rospy.Subscriber(topic_name_2, Float64Stamped, self.cb_c2)
        self.sub_c3 = rospy.Subscriber(topic_name_3, Float64Stamped, self.cb_c3)

        if self.checkValidC():
            print "Correct value on c"
        else:
            print "Wrong value on c, please retry"

    # callbacks for the distributions
    def cb_c0(self, data):
        # print "c0: ", data.data
        self.c0 = data.data

    def cb_c1(self, data):
        self.c1 = data.data

    def cb_c2(self, data):
        self.c2 = data.data

    def cb_c3(self, data):
        self.c3 = data.data

    def update_c(self):
        self.c[0] = self.c0
        self.c[1] = self.c1
        self.c[2] = self.c2
        self.c[3] = self.c3

    def pre_processing(self, filename='config/parameters.yaml'):
        with open(filename, 'r') as stream:
            try:
                yaml_data = yaml.safe_load(stream)

                # physical properties of the payload:
                J_base_P = box_inertia(yaml_data['payload']['base']['box']['x'],
                                            yaml_data['payload']['base']['box']['y'],
                                            yaml_data['payload']['base']['box']['z'],
                                            yaml_data['payload']['base']['mass'])
                J_holder_G = box_inertia(yaml_data['payload']['holder']['box']['x'],
                                            yaml_data['payload']['holder']['box']['y'],
                                            yaml_data['payload']['holder']['box']['z'],
                                            yaml_data['payload']['holder']['mass'])

                J_holders_O = \
                    [
                        deplacement_moment_inertia(
                            [-yaml_data['holder0']['origin']['x'],
                             -yaml_data['holder0']['origin']['y'],
                             -yaml_data['holder0']['origin']['z']], J_holder_G, yaml_data['payload']['holder']['mass']),
                        deplacement_moment_inertia(
                            [-yaml_data['holder1']['origin']['x'],
                             -yaml_data['holder1']['origin']['y'],
                             -yaml_data['holder1']['origin']['z']], J_holder_G, yaml_data['payload']['holder']['mass']),
                        deplacement_moment_inertia(
                            [-yaml_data['holder2']['origin']['x'],
                             -yaml_data['holder2']['origin']['y'],
                             -yaml_data['holder2']['origin']['z']], J_holder_G, yaml_data['payload']['holder']['mass']),
                        deplacement_moment_inertia(
                            [-yaml_data['holder3']['origin']['x'],
                             -yaml_data['holder3']['origin']['y'],
                             -yaml_data['holder3']['origin']['z']], J_holder_G, yaml_data['payload']['holder']['mass']),
                    ]
                self.mass_payload = yaml_data['payload']['base']['mass']
                mass_holder = yaml_data['payload']['holder']['mass']
                self.mass_payload = self.mass_payload + self.num_agents * mass_holder
                self.J_payload = J_base_P
                for j in range(self.num_agents):
                    self.J_payload = self.J_payload + J_holders_O[j]
                self.relative_pos = \
                    [
                        np.array([
                         yaml_data['holder0']['origin']['x'],
                         yaml_data['holder0']['origin']['y'],
                         yaml_data['quad']['base']['relative_height']
                        ]),

                        np.array([
                         yaml_data['holder1']['origin']['x'],
                         yaml_data['holder1']['origin']['y'],
                         yaml_data['quad']['base']['relative_height']
                        ]),

                        np.array([
                         yaml_data['holder2']['origin']['x'],
                         yaml_data['holder2']['origin']['y'],
                         yaml_data['quad']['base']['relative_height']
                        ]),

                        np.array([
                         yaml_data['holder3']['origin']['x'],
                         yaml_data['holder3']['origin']['y'],
                         yaml_data['quad']['base']['relative_height']
                        ])
                    ]

            except yaml.YAMLError as exc:
                print(exc)

    def checkValidC(self):
        return np.sum(self.c) == 1.0

    def calculateMatrixE(self):
        for i in range(self.num_agents):
            self.E_[i][0:3, 0:3] = np.eye(3)
            vv = self.relative_pos[i]
            self.E_[i][3:, 0:3] = skewsymetric(self.relative_pos[i])
            self.E_[i][3:, 3:] = np.eye(3)

    def updateSigma(self):
        sum = np.zeros((3, 3))
        for i in range(self.num_agents):
            S_ri = skewsymetric(self.relative_pos[i])
            sum = sum + np.multiply(self.c[i], np.dot(S_ri, S_ri.T))
        self.Sigma = np.eye(3) + sum

    def update_cE(self):
        self.update_c()
        self.updateSigma()
        for i in range(self.num_agents):
            self.E_inv[i][0:3, 0:3] = np.eye(3)
            self.E_inv[i][0:3, 3:] = -np.dot(skewsymetric(self.relative_pos[i]),
                                          np.linalg.inv(self.Sigma))
            self.E_inv[i][3:, 3:] = np.linalg.inv(self.Sigma)
            self.c_E[i] = self.c[i] * self.E_inv[i]
            print "c: ", self.c[i]

    def updateM0W0(self):
        for i in range(self.num_agents):
            self.M0_[i][:, :] = np.dot(
                np.dot(
                    self.E_inv[i], self.H0_
                )
                , np.linalg.inv(self.E_[i].T)
            )
            self.W0_[i] = np.dot(self.E_inv[i], self.G0_)

    def show_distribution(self):
        for i in range(self.num_agents):
            print "i: ", i
            print "M0: ", self.M0_
            print "W0: ", self.W0_

    def getM0(self, index=0):
        return self.M0_[index]

    def getW0(self, index=0):
        return self.W0_[index]

    def get_c(self, index=0):
        return self.c[index, 0]

    def setVerticesPosVel(self, positions, velocities):
        self.planner.setVerticesPosVel(positions, velocities)

    def get_d_trajectory(self, order, sample_frequency):
        self.planner.linear_opt.get_d_trajectory(order=order, sample_frequency=sample_frequency)

    def get_acceleratons(self, frequecy):
        self.get_d_trajectory(order=2, sample_frequency=frequecy)

    def generateDeiredTrj(self, positions, velocities):
        self.setVerticesPosVel(positions, velocities)
        self.planner.optimizeTimeAndFreeConstraints()

    def plot_derivatives(self, order):
        self.planner.linear_opt.plot_derivatives(order=order, solver='nonlinear')

    # def plot_consensus_history(self):
    #     self.consensor.plot_consensus_history()


if __name__ == '__main__':
    distributor = PayloadDistributor('hummingbird')
    distributor.generateDeiredTrj(positions=[[0.0, 0.0, 0.0],
                                             [2.0, 0.0, 2.0],
                                             [4.0, 0.0, 5.0]],
                                  velocities=[[0.0, 0.0, 0.0],
                                              [0.0, 0.0, 0.0],
                                              [0.0, 0.0, 0.0]])
    distributor.get_d_trajectory(order=0, sample_frequency=50)
    distributor.get_d_trajectory(order=1, sample_frequency=50)
    distributor.get_d_trajectory(order=2, sample_frequency=50)

    for i in range(100):
        distributor.update_c()
        distributor.update_cE()
        c_E = distributor.c_E
        distributor.updateM0W0()
        distributor.show_distribution()
    distributor.plot_consensus_history()
    distributor.plot_derivatives(order=0)
    distributor.plot_derivatives(order=1)
    distributor.plot_derivatives(order=2)



