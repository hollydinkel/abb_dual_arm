#!/usr/bin/env python3

import rospy
import moveit_commander
import numpy as np
import json
import os
import sys
import argparse
from geometry_msgs.msg import Pose
from visualization_msgs.msg import Marker
from visualization_msgs.msg import MarkerArray

def create_marker_array(points, color, min_frac=0.0, frame_id="world"):
    marker_array = MarkerArray()
    marker_id = 0
    for point in points:
        marker = Marker()
        marker.header.frame_id = frame_id
        marker.header.stamp = rospy.Time.now()
        marker.ns = "reachable_points"
        marker.id = marker_id
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position.x = point[0]
        marker.pose.position.y = point[1]
        marker.pose.position.z = point[2]
        marker.pose.orientation.x = 0.0
        marker.pose.orientation.y = 0.0
        marker.pose.orientation.z = 0.0
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.02
        marker.scale.y = 0.02
        marker.scale.z = 0.02
        marker.color.a = 1.0
        # Interpolate color based on planning fraction value
        if len(point) > 3:
            red = 1 - (point[3] - min_frac) / (1.0 - min_frac)
            green = 0
            blue = (point[3] - min_frac) / (1.0 - min_frac)
            color = [red, green, blue]
        marker.color.r = color[0]
        marker.color.g = color[1]
        marker.color.b = color[2]
        marker_array.markers.append(marker)
        marker_id += 1
    return marker_array

def publish_config_points(config_file):
    try:
        with open(config_file, 'r') as file:
            data = json.load(file)
    except json.JSONDecodeError:
        print("Error parsing JSON data.")
        return None
    marker_array = create_marker_array(data["fractions"])
    reachable_pub = rospy.Publisher('/abb_control/reachability_config', MarkerArray, queue_size=10)
    
    while not rospy.is_shutdown():
        reachable_pub.publish(marker_array)

def main():

    parser = argparse.ArgumentParser(description="Compute reachable workspace")
    parser.add_argument("path", help="Indicate config folder path")
    parser.add_argument("config", help="Indicate true to publish existing config")

    args = parser.parse_args()

    rospy.init_node('reachability', anonymous=True)

    file_path = f"{args.path}" + "/abb_control/config/config.json"

    if args.config == "true":
        publish_config_points(file_path)
    else:
        try: 
            os.mkdir(f"{args.path}/abb_control/config/")
        except FileExistsError:
            print("config directory already exists!")

        robot = moveit_commander.RobotCommander()

        # Initialize MoveIt commander
        moveit_commander.roscpp_initialize(sys.argv)

        group = moveit_commander.MoveGroupCommander("mp_m")

        # Define the workspace boundaries and resolution in world frame
        bounds = [-0.5, 0.5, -0.3, 0.4, 0.0, 0.6]
        resolution = 0.05
        x_vals = np.arange(bounds[0], bounds[1], resolution)
        y_vals = np.arange(bounds[2], bounds[3], resolution)
        z_vals = np.arange(bounds[4], bounds[5], resolution)
        grid_points = np.array(np.meshgrid(x_vals, y_vals, z_vals)).T.reshape(-1, 3)

        reachability = {"reachable_points" : [],
                        "unreachable_points": [],
                        "fractions": []}

        min_frac = 1.0
        for point in grid_points:
            pose_target = Pose()
            pose_target.position.x = point[0]
            pose_target.position.y = point[1]
            pose_target.position.z = point[2]
            pose_target.orientation.w = 1.0

            waypoints = []
            waypoints.append(group.get_current_pose().pose)
            waypoints.append(pose_target)
            (plan, fraction) = group.compute_cartesian_path(waypoints, 0.01, 0.0, avoid_collisions=True)
            if plan and fraction == 1.0:
                reachability["reachable_points"].append(point.tolist())
            else:
                if fraction < min_frac:
                    min_frac = fraction
                reachability["unreachable_points"].append(point.tolist())
            point_list = point.tolist()
            point_list.append(fraction)
            reachability["fractions"].append(point_list)
        
        with open(file_path, 'w') as json_file:
            json.dump(reachability, json_file, indent=4)

        # Create a marker array for visualization
        marker_array_1 = create_marker_array(reachability["reachable_points"],[0,0,1])
        marker_array_2 = create_marker_array(reachability["unreachable_points"],[1,0,0])
        marker_array_3 = create_marker_array(reachability["fractions"][:-1], [0,0,0], min_frac=min_frac)

        # Publish the marker array to RViz
        reachable_pub = rospy.Publisher('/abb_control/reachable_points', MarkerArray, queue_size=10)
        unreachable_pub = rospy.Publisher('/abb_control/unreachable_points', MarkerArray, queue_size=10)
        scaled_pub = rospy.Publisher('/abb_control/reachability', MarkerArray, queue_size=10)
        while not rospy.is_shutdown():
            reachable_pub.publish(marker_array_1)
            unreachable_pub.publish(marker_array_2)
            scaled_pub.publish(marker_array_3)
            rospy.sleep(1)

        moveit_commander.roscpp_shutdown()

if __name__ == '__main__':
    main()
