import os
import numpy as np
from gym import spaces
import mujoco_py

from .base_controller import BaseController
from . import register_controller

class InverseDynamicsController(BaseController):
    '''
    An inverse dynamics controller that used PD gains to compute a desired acceleration.
    '''

    def __init__(self,
                 sim,
                 model_path='full_kuka_no_collision_no_gravity.xml',
                 kp_id=100.,
                 kd_id='auto'):
        super(InverseDynamicsController, self).__init__(sim)
        
        # Create a model for control
        model_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), '..','envs', 'assets', model_path)
        self.model = mujoco_py.load_model_from_path(model_path)

        # Construct the action space.
        low = self.model.jnt_range[:, 0]
        high = self.model.jnt_range[:, 1]
        self.action_space = spaces.Box(low, high, dtype=np.float32)
        
        # Controller parameters.
        self.kp_id = kp_id
        if kd_id == 'auto':
            self.kd_id = 2 * np.sqrt(self.kp_id)
        else:
            self.kd_id = kd_id

        # Initialize setpoint.
        self.qpos_set = np.zeros(7)
        self.qvel_set = np.zeros(7)
 
    def set_action(self, action):
        '''
        Set the setpoint.
        '''
        self.qpos_set = action[:7]

    def get_torque(self):
        '''
        Update the PD setpoint and compute the torque.
        '''
        # Compute position and velocity errors
        qpos_err = self.qpos_set - self.sim.data.qpos
        qvel_err = self.qvel_set - self.sim.data.qvel

        # Compute desired acceleration using inner loop PD law
        self.sim.data.qacc[:] = self.kp_id * qpos_err + self.kd_id * qvel_err
        mujoco_py.functions.mj_inverse(self.model, self.sim.data)
        id_torque = self.sim.data.qfrc_inverse[:]

        # Sum the torques
        return id_torque

class RelativeInverseDynamicsController(InverseDynamicsController):
    def set_action(self, action):
        # Set the setpoint difference from the current position.
        self.qpos_set = self.sim.data.qpos + action[:7]

register_controller(InverseDynamicsController, 'InverseDynamicsController')
register_controller(RelativeInverseDynamicsController, 'RelativeInverseDynamicsController')