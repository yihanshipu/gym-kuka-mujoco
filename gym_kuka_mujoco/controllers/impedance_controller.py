import os

import numpy as np
from gym import spaces
import mujoco_py

from gym_kuka_mujoco.utils.quaternion import identity_quat, subQuat, quatIntegrate, mat2Quat
from gym_kuka_mujoco.utils.kinematics import forwardKinSite, forwardKinJacobianSite
from .base_controller import BaseController

class ImpedanceController(BaseController):
    '''
    An inverse dynamics controller that used PD gains to compute a desired acceleration.
    '''

    def __init__(self,
                 pos_scale=0.1,
                 rot_scale=0.5,
                 model_path='full_kuka_no_collision_no_gravity.xml'):
        super(ImpedanceController, self).__init__()
        
        # Create a model for control
        model_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), '..','envs', 'assets', model_path)
        self.model = mujoco_py.load_model_from_path(model_path)

        # Construct the action space.
        high_pos = np.inf*np.ones(3)
        low_pos = -high_pos

        high_rot = np.inf*np.ones(3)
        low_rot = -high_rot

        high = np.concatenate((high_pos, high_rot))
        low = np.concatenate((low_pos, low_rot))
        self.action_space = spaces.Box(low, high, dtype=np.float32)

        # Controller parameters.
        self.scale = np.ones(6)
        self.scale[:3] *= pos_scale
        self.scale[3:6] *= rot_scale

        self.pos_set = np.zeros(3)
        self.quat_set = identity_quat.copy()

        self.stiffness = np.array([1., 1., 1., .1, .1, .1])
        self.damping = 0.

    def set_action(self, action, sim):
        '''
        Set the setpoint.
        '''
        action = action * self.scale

        dx = action[0:3].astype(np.float64)
        dr = action[3:6].astype(np.float64)

        pos, mat = forwardKinSite(sim, 'peg_tip')
        quat = mat2Quat(mat)

        self.pos_set = pos + dx
        self.quat_set = quatIntegrate(quat, dr)

    def get_torque(self, sim):
        '''
        Update the impedance control setpoint and compute the torque.
        '''
        # Compute the pose difference.
        pos, mat = forwardKinSite(sim, 'peg_tip')
        quat = mat2Quat(mat)
        dx = self.pos_set - pos
        dr = subQuat(self.quat_set, quat)
        dframe = np.concatenate((dx,dr))

        # Compute generalized forces from a virtual external force.
        jpos, jrot = forwardKinJacobianSite(sim, 'peg_tip')
        J = np.vstack((jpos, jrot))
        external_force = J.T.dot(self.stiffness*dframe) # virtual force on the end effector

        # Cancel other dynamics and add virtual damping using inverse dynamics.
        acc_des = -self.damping*sim.data.qvel
        sim.data.qacc[:] = acc_des
        mujoco_py.functions.mj_inverse(self.model, sim.data)
        id_torque = sim.data.qfrc_inverse[:]
        
        return id_torque + external_force