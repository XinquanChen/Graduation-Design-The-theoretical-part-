# coding=utf-8
import random
from  my_motion_planning_toolbox import *
import os
from queue import PriorityQueue
# https://www.jianshu.com/p/eaa1bf01b3a6
import yaml
def generate_yaml_doc(yaml_file,py_object):
    file = open(yaml_file, 'w', encoding='utf-8')
    yaml.dump(py_object, file)
    file.close()
def get_yaml_data(yaml_file):
    # 打开yaml文件
    file = open(yaml_file, 'r', encoding="utf-8")
    file_data = file.read()
    file.close()
    # 将字符串转化为字典或列表
    data = yaml.safe_load(file_data)
    return data
# Load Global Variable
current_path = os.path.abspath(".")
yaml_path = os.path.join(current_path, "my_motion_roadmap.yaml")
data = get_yaml_data(yaml_path)
CIRCLE_R = data['CIRCLE_R']  # 机器人以及动态障碍物的半径(假设都是圆)
POINT_GOAL = tuple(data['POINT_GOAL'])  # 全局目标
POINT_START = tuple(data['POINT_START'])  # 全局起始点
DYNAMIC_DEFAULT_COLOR = tuple(data['DYNAMIC_DEFAULT_COLOR'])  # 动态障碍物的颜色
DYNAMIC_VISIBLE_R = data['DYNAMIC_VISIBLE_R']  # 人的可视范围(假设是方形区域)的半径
REACH_GOAL_THRESHOLD = data['REACH_GOAL_THRESHOLD']
ROBOT_SPEED = data['ROBOT_SPEED']  # 机器人的速度
ROBOT_COLOR = tuple(data['ROBOT_COLOR'])  # 机器人的颜色
ROBOT_VISIBLE_R = data['ROBOT_VISIBLE_R']  # 机器人的可视范围(假设是方形区域)的半径
num_key = data['num_key']
ROBOT_CONTROL = data['ROBOT_CONTROL']
STEP_REWARD = data['STEP_REWARD']  # 机器人走一步的代价
COLLISION_REWARD = data['COLLISION_REWARD']  # 机器人发生碰撞的代价
REACH_GOAL_REWARD = data['REACH_GOAL_REWARD']  # 机器人到达终点的奖励
MAX_ATTRACTIVE = data['MAX_ATTRACTIVE']
'''
step一般是用于计算动力学方程更新参数和reward的，是物理引擎，返回
  observation
  reward
  done :判断是否到了重新设定(reset)环境
  info :用于调试的诊断信息，有时也用于学习，但智能体（agent ）在正式的评价中不允许使用该信息进行学习。
render是图像引擎用来显示环境中的物体图像
  from gym.envs.classic_control import rendering
  # 这一句导入rendering模块，利用rendering模块中的画图函数进行图形的绘制
  self.viewer = rendering.Viewer(600, 400)   # 600x400 是画板的长和框
  line1 = rendering.Line((100, 300), (500, 300))
  line2 = rendering.Line((100, 200), (500, 200))
  # 给元素添加颜色
  line1.set_color(0, 0, 0)
  line2.set_color(0, 0, 0)
  # 把图形元素添加到画板中
  self.viewer.add_geom(line1)
  self.viewer.add_geom(line2)
  return self.viewer.render(return_rgb_array=mode == 'rgb_array')
  gym rendering 画图模块
  具体参考：https://www.jianshu.com/p/bb5a7116d189
  这里我们先使用cv2,在之后再重构
进程通过调用reset()来启动，它返回一个初始observation
'''
# WARNNIG:由于简单的使用opencv作为显示,所以所有位置x,y 以索引格式得到图片上相应像素的时候需要 img[y,x]
# 为什么会产生这个问题尚未明了
#-------------------------------------------------------------------
class Dynamic(object):
    def __init__(self,route):
        self.point_color = DYNAMIC_DEFAULT_COLOR
        self.point_size = CIRCLE_R
        self.thickness = -1  # 可以为 0 、4、8 边框宽度 -1为填充
        self.route = route
        self.speed = len(self.route)
        self.current_step = 0
        self.dynamic_visible_r = DYNAMIC_VISIBLE_R
    def step(self):
        self.current_step = self.current_step + 1
        self.current_step = self.current_step % self.speed
        observation = self.getLocation()
        reward = 0
        done = False
        info = None
        return [observation,reward,done,info]
    # WARNNIG:由于简单的使用opencv作为显示,所以所有位置x,y 以索引格式得到图片上相应像素的时候需要 img[y,x]
    # 貌似调用opencv circle line函数都是(x,y) 维度索引是反的
    def render(self,mr):
        if isinstance(mr,MotionRoadmap):
            cv2.circle(mr.get_current_map(), self.getLocation(), self.point_size, \
                       self.point_color, self.thickness)
            x,y = self.getLocation()
            x_1,x_2,y_1,y_2 = mr.range_in_map(x-self.dynamic_visible_r,x+self.dynamic_visible_r,\
                                              y-self.dynamic_visible_r,y+self.dynamic_visible_r)
            return mr.get_current_map()[y_1:y_2,x_1:x_2]
        else:
            cv2.circle(mr,self.getLocation(),self.point_size,self.point_color,self.thickness)
            return mr
    def getLocation(self):
        x, y = self.route[self.current_step]
        return (int(x),int(y))
    def reset(self):
        self.current_step = 0
        return self.getLocation()
class Circle_man(Dynamic):
    def __init__(self, r, a, b, speed):
        self.r = r
        self.a, self.b = (a, b)
        self.speed = speed
        self.theta = np.arange(0, 2 * np.pi, 2 * np.pi/speed)
        self.route = [(int(self.a + self.r * np.cos(i)), int(self.b + self.r * np.sin(i))) \
                      for i in self.theta]
        Dynamic.__init__(self, self.route)
    def info(self):
        return "I am Circle_man,a:"+str(self.a)+",b:"+str(self.b)+",and r:"+str(self.r)
class Linear_man(Dynamic):
    def __init__(self, start, end, speed):
        self.x1, self.y1 = start
        self.x2, self.y2 = end
        self.speed = speed
        half_speed = int(speed/2) #半个周期就要走完两个点,然后再折返,否则会闪现
        x_gap = (self.x2 - self.x1)/ half_speed
        y_gap = (self.y2 - self.y1)/ half_speed
        if x_gap!=0:
            x = np.arange(self.x1 , self.x2, x_gap)
        else:
            x = np.ones(self.speed)*self.x1
        if y_gap!=0:
            y = np.arange(self.y1 , self.y2,y_gap)
        else:
            y = np.ones(self.speed)*self.y1
        self.route = [ (x[i], y[i]) for i in range(half_speed)]
        self.route += [ (x[i], y[i]) for i in range(half_speed-1,-1,-1)]
        Dynamic.__init__(self, self.route)
    def info(self):
        return "I am Linear_man,x1:"+str(self.x1)+",y1:"+str(self.y1)+",and x2:"+str(self.x2)+",y2:"+str(self.y2)
class Robot(Dynamic):
    def __init__(self,point_start,point_goal,speed = ROBOT_SPEED,visible_r = ROBOT_VISIBLE_R):
        Dynamic.__init__(self, [point_start])
        self.route = [point_start]
        self.point_start = point_start
        self.point_goal = point_goal
        self.RobotLocation = point_start
        self.point_color = ROBOT_COLOR
        self.speed = speed
        self.visible_r = visible_r
    def step(self,action):
        x, y = self.getLocation()
        if isinstance (action,int):# 一般使用cv2.waitkey得到的数字(其实对应的是按键的ascii)
            delta_x,delta_y = ROBOT_CONTROL.get(action,(0,0))#如果按到其他没有的key 则返回（0,0）
        elif isinstance(action, tuple):
            delta_x,delta_y = action  # 如果按到其他没有的key 则返回（0,0）
        else:
            raise("Error type")
        x = x + delta_x * self.speed
        y = y + delta_y * self.speed
        self.RobotLocation = (x, y)
        self.route.append(self.RobotLocation)
        self.current_step = self.current_step + 1
        observation = self.RobotLocation
        reward = 0
        done = False
        if (x,y)==self.point_goal:
            done = True
        info = None
        return [observation,reward,done,info]
    def getLocation(self):
        return self.RobotLocation
    def reset(self):
        self.RobotLocation = self.point_start
        self.route = [self.point_start]
        self.current_step = 0
        return self.RobotLocation
    def getRoute(self):
        return self.route
class MotionRoadmap(object):
    def __init__(self, map_img):
        ## 初始化实例，需要输入一张 bmp 格式的地图
        self.static_map = map_img.copy()
        self.current_map = map_img.copy()
        # 读取图像尺寸
        self.size = self.static_map.shape
        self.x_max = self.size[0]
        self.y_max = self.size[1]
        # 运动规划的起点
        self.point_start = POINT_START
        # 运动规划的终点
        self.point_goal = POINT_GOAL
        # 对静态地图进行膨胀,时间复杂度较高，不建议经常调用(这里建议地图的静态障碍物是黑色的,因为下面碰撞检测是检测黑色)
        KERNEL = np.ones(((CIRCLE_R-1)*2, (CIRCLE_R-1)*2), np.uint8)  # 膨胀 20
        self.collision_map = cv2.cvtColor(cv2.erode(map_img, KERNEL), cv2.COLOR_BGR2GRAY)
        # 静态障碍物坐标
        img_gray = cv2.cvtColor(self.static_map, cv2.COLOR_BGR2GRAY)
        ret, img_binary = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY)
        temp = np.argwhere(img_binary == [0])
        self.position_obs = np.append(temp[:, 1].reshape(-1, 1), temp[:, 0].reshape(-1, 1), axis=1)
        # 全地图最近障碍物是否给出的标志位
        self.d_min = False
    def get_static_map(self):
        return self.static_map.copy()  # 转为RGB显示
    def get_collision_map(self):
        return self.collision_map  # 转为RGB显示
    def get_current_map(self):
        return self.current_map
    def set_current_map(self,img):
        self.current_map = img
    def reach_goal(self,point):
        if straight_distance(point,self.point_goal) <= REACH_GOAL_THRESHOLD:
            return True
        return False
    def point_in_map(self,point):
        x, y = point
        if x < self.x_max and y < self.y_max and x >= 0 and y >= 0:
            return True
        else:
            return False
    def range_in_map(self,x_start,x_end,y_start,y_end):
        if x_start < 0:
            x_start = 0
        if x_start >= self.x_max:
            x_start = self.x_max - 1
        if x_end < 0:
            x_end = 0
        if x_end >= self.x_max:
            x_end = self.x_max - 1
        if y_start < 0:
            y_start = 0
        if y_start >= self.y_max:
            y_start = self.y_max - 1
        if y_end < 0:
            y_end = 0
        if y_end >= self.y_max:
            y_end = self.y_max - 1
        return x_start,x_end,y_start,y_end
    def static_collision_detection(self, point):
        x, y = point
        feasibility = True
        if self.point_in_map(point):
            # 这里输入的是x,y 但是图片坐标是反过来的
            color = self.collision_map[y, x]
            if  color == 0 :# 二值化之后黑色(障碍物)为0(这里最好该一下,如果别人不用黑色表示障碍物就会出错)
                feasibility = False
        else:
            feasibility = False
        return feasibility
    def static_check_path(self,point_current, point_other):
        x1, y1 = point_current
        x2, y2 = point_other
        '''路径检查的采样点数，取路径横向与纵向长度的较大值，保证每个像素都能验证到'''
        step_length = int(max(abs(x1 - x2), abs(y1 - y2)))
        path_x = np.linspace(x1, x2, step_length + 1)
        path_y = np.linspace(y1, y2, step_length + 1)
        for i in range(int(step_length + 1)):
            if not self.static_collision_detection([math.ceil(path_x[i]), math.ceil(path_y[i])]):
                return False
        return True
#-------------------------------------------------------------------
class DynamicEnv(MotionRoadmap):
    motion_direction = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1), (0, 0)]
    D_min = 2 * CIRCLE_R
    D_max = 8 * CIRCLE_R
    def __init__(self,map_img,crowd_list,robot):
        MotionRoadmap.__init__(self,map_img)
        self.crowd_list = crowd_list
        self.Robot = robot
        self.current_map = self.render()
        self.done = False
        self.reward = 0
        self.APF_WAY = APF_WAY
        self.point_start=self.Robot.getLocation()
        self.vertex_exit = False
        self.adjacency_mat_exit = False
    def render(self):#图像引擎的计算，得到全局的图像current_map
        self.set_current_map(self.get_static_map())
        for person in self.crowd_list:
            person.render(self)
        self.Robot.render(self)
        img_copy = self.get_current_map().copy()
        cv2.circle(img_copy, self.point_start, 10, (255,200,0), -1)
        cv2.circle(img_copy, self.point_goal, 10, (255, 100, 0), -1)
        return img_copy
    #step可以传入键盘的key int num,也可以传入tuple
    def step(self, action):#作出一个动作，进行物理计算，并且得到相应的done，reward，observation，（info）
        for person in self.crowd_list:
            person.step()
        self.Robot.step(action)#这里之后需要修改成依照算法决策，而不是环境的step给的
        r_x,r_y = self.Robot.getLocation()
        #检查是否和动态或者静态障碍物接触，接触了就-10分
        if not self.static_collision_detection((r_x,r_y)) or not self.crowd_collision_detection((r_x,r_y)):
            if not self.static_collision_detection((r_x,r_y)):
                print("撞墙!")
            if not self.crowd_collision_detection((r_x,r_y)):
                print("撞人!")
            done = True
            reward = COLLISION_REWARD
        #检查是否到达重点
        elif self.reach_goal((r_x,r_y)):
            done = True
            reward = REACH_GOAL_REWARD
        else:
            done = False
            reward = STEP_REWARD
        observation = None
        self.reward += reward
        self.done = done
        info = None
        return [observation,reward,done,info]
    def reset(self):#重置所有状态，并且返回初始的observation
        for person in self.crowd_list:
            person.reset()
        self.Robot.reset()
        self.render()
        self.done = False
        self.reward = 0
        return None
    def crowd_density_point(self,point,radius):
        density = 0
        for person in self.crowd_list:
            if straight_distance(person.getLocation(),point)<radius:
                density = density + 1
        return density
    def crowd_collision_detection(self,point):
        for person in self.crowd_list:
            if straight_distance(point,person.getLocation()) < (self.Robot.point_size + person.point_size):
                return False
        return True
    def crowd_check_path(self,point_current, point_other):
        x1, y1 = point_current
        x2, y2 = point_other
        ## 路径检查的采样点数，取路径横向与纵向长度的较大值，保证每个像素都能验证到
        step_length = int(max(abs(x1 - x2), abs(y1 - y2)))
        path_x = np.linspace(x1, x2, step_length + 1)
        path_y = np.linspace(y1, y2, step_length + 1)
        for i in range(step_length + 1):
            if not self.crowd_collision_detection([math.ceil(path_x[i]), math.ceil(path_y[i])]):
                return False
        return True
    #-------------------------------------------------------------------PRM输出项
    def prm_planning(self, **param):
        vertex, adjacency_mat = self.prm(**param)
        sign,path,img = self.A_star(vertex, adjacency_mat)
        return sign,path,img
    def danger_all(self,point_a,point_b):
        if point_a==None or point_b==None or point_a==point_b:
            return Vector(-1,-1)
        dan = Vector(0,0)
        for person in self.crowd_list:
            dan = dan+self.danger(point_a,point_b,person.route)
        return dan
    def danger(self,point_a,point_b,route):
        D = []
        x1, y1 = point_a
        x2, y2 = point_b
        ## 路径检查的采样点数，取路径横向与纵向长度的较大值，保证每个像素都能验证到
        step_length = int(straight_distance(point_a,point_b)/CIRCLE_R)
        path_x = np.linspace(x1, x2, step_length + 1)
        path_y = np.linspace(y1, y2, step_length + 1)
        for i in range(step_length + 1):
            point = [math.ceil(path_x[i]), math.ceil(path_y[i])]
            temp_D = []
            for point_c in route:
                d = straight_distance(point_c,point)
                temp_D.append(d)
            d_min, d_max = min(temp_D), max(temp_D)
            D.append(d_min)
        d_min , d_max = min(D),max(D)
        if d_min <= self.D_min:
            Danger_max = 1
        elif d_min >= self.D_max:
            Danger_max = 0
        else:
            Danger_max = 1 - d_min / self.D_max
        if d_max <= self.D_min:
            Danger_min = 1
        elif d_max >= self.D_max:
            Danger_min = 0
        else:
            Danger_min = 1 - d_max / self.D_max
        return Vector(Danger_min,Danger_max)
    def prm(self,**param):#输出的不联通或者相同点必须第一维度是-1
        if self.vertex_exit and self.adjacency_mat_exit:
            print("PRM already exist")
            return self.vertex,self.adjacency_mat
        print('开始 PRM ，请等待,PRM对象是Full Observed,时间为t0时的地图...')
        # 关键字参数处理
        self.num_sample = 5
        distance_neighbor = 600
        show = False
        if 's' in param:
            self.num_sample = param['s']
        if 'n' in param:
            distance_neighbor = param['n']
        if 'show' in param:
            show = param['show']
        if not ('p' in param):
            param['p'] = True
        if 'vertex' in param:
            vertex = param['vertex']
            self.num_sample = len(vertex) - 2
        else:
            ## 构造地图
            # 采样并添加顶点
            vertex = [self.point_start, self.point_goal]
            while len(vertex) < (self.num_sample + 2):
                x = random.randint(0, self.x_max)
                y = random.randint(0, self.y_max)
                if self.static_collision_detection((x, y)):
                    vertex.append((x, y))
        if show:
            img = self.world_distribution()
            for i in vertex:
                cv2.circle(img, i, 4, (255, 100, 100), -1)
        ## 构造邻接矩阵
        adjacency_mat = np.ones((self.num_sample + 2, self.num_sample + 2, 3 )) *(-1)
        for i in range(self.num_sample + 2):
            for j in range(self.num_sample + 2):
                length = straight_distance(vertex[i], vertex[j])
                if self.static_check_path(vertex[i],vertex[j]) and length <distance_neighbor and length > 3.0:
                    adjacency_mat[i, j, 0] = length  # 邻接矩阵置为1
                    vector =  self.danger_all(vertex[i],vertex[j])
                    adjacency_mat[i,j,1] = vector.get_min()
                    adjacency_mat[i,j,2] = vector.get_max()
                    if show and length!=-1:
                        cv2.line(img,vertex[i],vertex[j],(450*adjacency_mat[i,j,1],450*adjacency_mat[i,j,1],450*adjacency_mat[i,j,1]))
                        a = vertex[i]
                        b = vertex[j]
                        cv2.putText(img, str(adjacency_mat[i, j]), (int( (a[0]+b[0])/2 ),int( (a[1]+b[1])/2 )), \
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 20, 0), 1)
        self.vertex = vertex
        self.adjacency_mat = adjacency_mat
        self.vertex_exit = True
        self.adjacency_mat_exit = True
        if show:
            cv2.imshow("prm",img)
            cv2.waitKeyEx(0)
        return vertex,adjacency_mat
    def A_star(self,vertex,adjacency_mat):
        ## A*算法搜索最佳路径
        self.close_list, self.find = self.new_A_star_algorithm(vertex, adjacency_mat, 0, 1)
        if (self.find == True):
            path,img = self.new_A_star_plot(self.render(), vertex, adjacency_mat, self.close_list,0,1)
            return True,path,img
        else:
            print('没有找到解，无法绘图！')
        return  False,[],None
    def neighbors(self,adjacency_mat,current_index):
        result = []
        for i in range(self.num_sample+2):
            if adjacency_mat[current_index,i,0] != -1:
                result.append(i)
        return result
    #-------------------------------------------------------------------PP
    def new_A_star_algorithm(self,vertex,adjacency_mat,start_index,goal_index):
        ## A*搜索算法
        print("开始Dynamic Env的new_A_star_algorithm")
        frontier = PriorityQueue()
        cost_so_far = {}
        cost_so_far[start_index] = 0
        frontier.put((cost_so_far[start_index],start_index))
        came_from = {}
        came_from[start_index]=None
        find = False
        while not frontier.empty():
            priority,current_index = frontier.get()
            for next_index in self.neighbors(adjacency_mat,current_index):
                new_cost = cost_so_far[current_index] + straight_distance(vertex[next_index],vertex[current_index])
                if next_index not in cost_so_far or new_cost<cost_so_far[next_index]:
                    cost_so_far[next_index] = new_cost
                    next_priority = new_cost + straight_distance(vertex[next_index],vertex[goal_index])
                    frontier.put((next_priority,next_index))
                    came_from[next_index] = current_index
            if current_index == goal_index:#没有注释掉的话 貌似找不到最短路径
                find = True
                break
        return came_from,find
    def new_A_star_plot(self,map_img, vertex, adjacency_mat, close_list,start_index, goal_index):
        for i in vertex:
            cv2.circle(map_img, i, 5, (255, 100, 100), -1)
        for i in range(self.num_sample + 2):
            for j in range(self.num_sample + 2):
                if adjacency_mat[i,j,0] != -1:
                    cv2.line(map_img,vertex[i],vertex[j],(450*adjacency_mat[i,j,1],450*adjacency_mat[i,j,2],0))
        next_index = close_list[goal_index]
        path = [goal_index,next_index]
        while next_index!=start_index:
            path.append(close_list[next_index])
            next_index = close_list[next_index]
        length = len(path)
        for i in range(length-1):
            cv2.line(map_img,vertex[path[i]],vertex[path[i+1]],(255,0,0),3)
        return path,map_img
    '''https://blog.csdn.net/junshen1314/article/details/50472410'''
    # 局部规划
    def apf_static(self, point):
        d_min = find_nearest_obstacle_distance(self.position_obs, point)
        if self.APF_WAY == 0:
            uo = APF_function(d_min)
        elif self.APF_WAY == 1:
            uo = my_APF_function(d_min)
        elif self.APF_WAY == 2:
            uo = improved_APF_function(d_min,straight_distance(point, self.point_goal))
        elif self.APF_WAY == 3:
            uo = my_improved_APF_function(d_min, straight_distance(point, self.point_goal))
        return uo
    def apf_dynamic(self,point):
        Repulsive = []
        # 障碍物的斥力场 uo  d_min:最近障碍物的距离 也就是距离的最小值
        for person in self.crowd_list:
            D = straight_distance(person.getLocation(),point)
            uo = OBSTACLE_MAX
            if D > CIRCLE_R:# 在CIRCLE_R*2之内的都是OBSTACLE_MAX
                if self.APF_WAY == 0:
                    uo = APF_function(D)  # 3 rou的时候接近0
                elif self.APF_WAY == 1:
                    uo = my_APF_function(D)  # 3 rou的时候接近0
                elif self.APF_WAY == 2:
                    uo = improved_APF_function(D, straight_distance(point, self.point_goal))
                elif self.APF_WAY == 3:
                    uo = my_improved_APF_function(D, straight_distance(point, self.point_goal))
            Repulsive.append(uo)
        return Repulsive
    def apf_goal(self,point, goal):
        return straight_distance(point,goal)
    def apf_cul(self,location,goal):
        if self.static_collision_detection(location):# 没有发生静态碰撞
            repulsive = self.apf_static(location) + sum(self.apf_dynamic(location))
            attractive = self.apf_goal(location,goal)/MAX_ATTRACTIVE * OBSTACLE_MAX
            return  attractive + repulsive
        else:
            return OBSTACLE_MAX
    '''得到location这一点周围梯度最大的下一点,并且输出'''
    def apf_next_guide(self,location,next_goal):
        potential_current = self.apf_cul(location, next_goal)
        D = (0,0)#如果陷入局部最优 有一定概率要随机游走
        for d in self.motion_direction:  # 选出梯度最大的那一个点
            index_x = location[0] + d[0] * CIRCLE_R
            index_y = location[1] + d[1] * CIRCLE_R
            if ((index_x < 0) or (index_x >= self.x_max) or
                    (index_y < 0) or (index_y >= self.y_max)):
                potential_next = float('inf')
            else:
                potential_next = self.apf_cul((index_x, index_y), next_goal)
            if potential_current > potential_next:
                potential_current = potential_next
                D = d
            if D == (0,0):
                if random.random() >0.4:
                    D = random.choice(self.motion_direction)
        return D
    #显示障碍物的范围
    def world_distribution(self, show=False):
        self.reset()
        img = self.get_static_map()
        for i in range(100):
            for person in self.crowd_list:
                person.render(img)
                person.step()
        cv2.circle(img, self.point_start, 10, (255, 200, 0), -1)
        cv2.circle(img, self.point_goal, 10, (255, 100, 0), -1)
        if show:
            cv2.imshow("world", img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return img
#-------------------------------------------------------------------
# 图像路径 我画的图片静态障碍物是（100,100）（400,300）的矩形 圆的r=15
# 横轴是x 从左到右变大 竖轴是y 从上到下变大
def world_0():
    image_path = "map_0.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((383, 125), (441, 64), 20))
    crowd_list.append(Circle_man(25, 110, 250, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 183, 218, 50))
    crowd_list.append(Circle_man(25, 240, 110, 15))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_1():
    image_path = "map_1.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((350, 90), (400, 15), 20))
    crowd_list.append(Linear_man((100, 400), (150, 350), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Circle_man(25, 50, 75, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 150, 45, 50))
    crowd_list.append(Circle_man(25, 250, 45, 15))
    crowd_list.append(Circle_man(25, 400, 400, 20))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_2():
    image_path = "map_2.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((350, 90), (400, 15), 20))
    crowd_list.append(Linear_man((100, 400), (150, 350), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Linear_man((200, 400), (400, 490), 80))
    crowd_list.append(Circle_man(25, 50, 75, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 150, 45, 50))
    crowd_list.append(Circle_man(25, 250, 45, 15))
    crowd_list.append(Circle_man(25, 400, 400, 20))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_3():
    image_path = "map_2.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((350, 90), (400, 15), 20))
    crowd_list.append(Linear_man((350, 400), (450, 450), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Linear_man((170, 300), (230, 200), 30))
    crowd_list.append(Circle_man(25, 50, 75, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 150, 45, 50))
    crowd_list.append(Circle_man(25, 250, 45, 15))
    crowd_list.append(Circle_man(10, 300, 200, 60))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_4():
    image_path = "map_3.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((350, 90), (400, 15), 20))
    crowd_list.append(Linear_man((350, 400), (450, 450), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Linear_man((170, 300), (230, 200), 30))
    crowd_list.append(Circle_man(25, 50, 75, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 150, 45, 50))
    crowd_list.append(Circle_man(25, 250, 45, 15))
    crowd_list.append(Circle_man(10, 300, 200, 60))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_5():
    image_path = "map_4.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((400, 200), (400, 15), 25))
    # crowd_list.append(Linear_man((300, 150), (450, 150), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Linear_man((60, 300), (100, 400), 30))
    crowd_list.append(Circle_man(15, 150, 140, 50))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 360, 300, 50))
    crowd_list.append(Circle_man(25, 250, 45, 15))
    # crowd_list.append(Circle_man(10, 300, 200, 60))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_6():
    image_path = "map_5.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((94, 1), (130, 50), 50))
    crowd_list.append(Linear_man((350, 400), (450, 450), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Circle_man(25, 50, 75, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 486, 249, 50))
    crowd_list.append(Circle_man(25, 250, 33, 15))
    crowd_list.append(Circle_man(10, 257, 156, 10))
    robot = Robot((25, 190), POINT_GOAL)
    return img,crowd_list,robot
def world_7():
    image_path = "map_6.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((319, 90), (380, 90), 10))  # 输入是start起点 end终点 period周期
    crowd_list.append(Circle_man(25, 250, 22, 25))  # 输入是r半径 (a,b)原点 speed period周期
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
def world_8():
    image_path = "map_7.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    img = cv2.resize(img, (500, 500))
    crowd_list = []
    crowd_list.append(Linear_man((313, 102), (383, 32), 20))
    crowd_list.append(Circle_man(25, 110, 250, 25))  # 输入是r半径 (a,b)原点 speed period周期
    crowd_list.append(Circle_man(25, 183, 218, 50))
    crowd_list.append(Circle_man(25, 240, 110, 15))
    robot = Robot(POINT_START, POINT_GOAL)
    return img,crowd_list,robot
#-------------------------------------------------------------------
'''
输入:
    mr:MotionRoadmap的子类,对于动态路径规划输入的是DynamicEnv动态环境,包含机器人和移动障碍物
    PRM_POINT_NUM:PRM算法采样的点数
    PRM_DISTANCE:判断可通行区域的距离
    foldname:结果保存的文件夹
'''
#-------------------------------------------------------------------
class Vector():
    """
    2维向量, 支持加法(A+B-A*B)以及大小比较
    a = b  for i in range(2):ai = bi
    a <= b for i in range(2):ai <= bi
    a < b for i in range(2):ai <= bi  && k = 1~2 ai < bi
    a << b for i in range(2):ai < bi
    """
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def __str__(self):
        return "{0},{1}".format(round(self.x,2),round(self.y,2))
    def __add__(self, other):
        x = self.x + other.x - self.x*other.x
        y = self.y + other.y - self.y*other.y
        return Vector(x,y)
    def __lt__(self,other):
        if self.x <= other.x and self.y <= other.y:
            if self.x < other.x or self.y < other.y:
                return True
        return False
    def __le__(self,other):
        if self.x <= other.x and self.y <= other.y:
            return True
        else:
            return False
    def __eq__(self,other):
        if self.x == other.x and self.y == other.y:
            return True
        else:
            return False
    def __gt__(self, other):
        if self.x >= other.x and self.y >= other.y:
            if self.x > other.x or self.y > other.y:
                return True
        return False
    def __ge__(self,other):
        if self.x >= other.x and self.y >= other.y:
            return True
        else:
            return False
    def get_min(self):
        return self.x
    def get_max(self):
        return self.y
class Cost():
    def __init__(self, length, section):
        self.length = length
        self.section = section
    def __str__(self):
        return "[{0},{1}]".format(int(self.length), self.section)
    def __add__(self, other):
        length = self.length + other.length
        section = self.section + other.section
        return Cost(length,section)
    def __lt__(self, other):
        if self.section < other.section:
            return True
        else:
            if self.section == other.section:
                if self.length < other.length:
                    return True
        return False
    def __le__(self, other):
        if self.section <= other.section:
            return True
        else:
            if self.section == other.section:
                if self.length <= other.length:
                    return True
        return False
    def __eq__(self, other):
        if self.length == other.length and self.section == other.section:
            return True
        else:
            return False
    def __gt__(self, other):
        if self.section > other.section:
            return True
        else:
            if self.section == other.section:
                if self.length > other.length:
                    return True
        return False
    def __ge__(self,other):
        if self.section >= other.section:
            return True
        else:
            if self.section == other.section:
                if self.length >= other.length:
                    return True
        return False
    def get_length(self):
        return self.length
    def get_section(self):
        return self.section
class DE1(DynamicEnv):
    pass
class DE2(DynamicEnv):
    def __init__(self,map_img,crowd_list,robot):
        DynamicEnv.__init__(self,map_img,crowd_list,robot)
    '''
    dDi_min = 1 if d_min<D_min  0 d_min>D_max d_min/D_max else
    dDi_max = 1 if d_min<D_min  0 d_max>D_max d_max/D_max else
    重写原有的danger方法
    '''
    def prm_planning(self, **param):
        vertex, adjacency_mat = self.prm(**param)
        return self.DE2_A_star(vertex, adjacency_mat)
    def DE2_A_star(self,vertex,adjacency_mat):
        ## A*算法搜索最佳路径
        self.close_list, self.find = self.DE2_A_star_algorithm(vertex, adjacency_mat, 0, 1)
        if (self.find == True):
            path,img = self.new_A_star_plot(self.render(), vertex, adjacency_mat, self.close_list,0,1)
            return True,path,img
        else:
            print('没有找到解，无法绘图！')
        return  False,[],None
    def DE2_A_star_algorithm(self,vertex, adjacency_mat, start_index, goal_index):
        ## A*搜索算法
        print("开始DE2的A_star_algorithm")
        frontier = PriorityQueue()
        cost_so_far = {}
        cost_so_far[start_index] = Cost(0,Vector(0,0))
        frontier.put((cost_so_far[start_index],start_index))
        came_from = {}
        came_from[start_index]=None
        find = False
        while not frontier.empty():
            priority,current_index = frontier.get()
            if current_index == goal_index:
                find = True
                break
            for next_index in self.neighbors(adjacency_mat,current_index):
                new_cost = self.A_star_cost(adjacency_mat,next_index,current_index,cost_so_far[current_index])
                if next_index not in cost_so_far or new_cost<cost_so_far[next_index]:
                    cost_so_far[next_index] = new_cost
                    priority = new_cost + self.A_star_heuristic(vertex,next_index,goal_index)
                    frontier.put((priority,next_index))
                    came_from[next_index] = current_index
        return came_from,find
    def A_star_heuristic(self,vertex,next_index,goal_index):
        ## A*算法的路径代价表计算工具
        vector = self.danger_all(vertex[next_index],vertex[goal_index])
        d_min = vector.get_min()
        d_max = vector.get_max()
        heuristic_cost = Cost(straight_distance(vertex[next_index],vertex[goal_index]),
                                Vector(d_min,d_max))
        total_cost =  heuristic_cost
        return total_cost
    def A_star_cost(self,adjacency_mat,next_index,current_index,historic_cost):
        ## A*算法的路径代价表计算工具
        ad = adjacency_mat[current_index, next_index]
        distance = ad[0]
        d_min = ad[1]
        d_max = ad[2]
        cost = Cost(distance,Vector(d_min,d_max))
        total_cost = historic_cost + cost
        return total_cost
class DE3(DynamicEnv):
    pass
def visualize_apf(img,mr,reward):
    assert isinstance(mr,MotionRoadmap)
    #  visualize apf
    x, y = mr.Robot.getLocation()
    for h in range(x - 50, x + 50):
        for u in range(y - 50, y + 50):
            apf = mr.apf_cul((h, u), mr.point_goal)
            cv2.circle(img, (h, u), 1, (apf, apf, apf), -1)
    if reward == COLLISION_REWARD:
        cv2.circle(img, (x, y), 10, (100, 200, 150), -1)
    else:
        cv2.circle(img, (x, y), 10, (255, 255, 0), -1)
    cv2.circle(img, mr.point_goal, 5, (255, 100, 0), 1)
    return img
#-------------------------------------------------------------------
#PRM正确性的test  能够很好的表示通路的危险程度
def test_PRM():
    image_path = "map_7.bmp"
    img = cv2.imread(image_path)  # np.ndarray BGR uint8
    crowd_list = []
    crowd_list.append(Linear_man((180, 130), (95, 250), 20))#0,0.69
    crowd_list.append(Linear_man((180, 160), (95, 280), 20))#0,0.47
    # crowd_list.append(Linear_man((180, 130), (180, 250), 20))#0,0
    # crowd_list.append(Linear_man((180, 130), (150, 250), 20))#0,0.24
    # crowd_list.append(Linear_man((150, 130), (150, 250), 20))# 0,0.38
    # crowd_list.append(Linear_man((130, 130), (130, 250), 20))#0,0.62
    # crowd_list.append(Linear_man((130, 100), (130, 150), 20))#0,0.62
    # crowd_list.append(Linear_man((130, 140), (130, 160), 20))#0.16,0.62
    # crowd_list.append(Linear_man((180, 130), (95, 250), 20))
    POINT_GOAL = (150,50)
    robot = Robot(POINT_START, POINT_GOAL)
    mr  =  DE2(img,crowd_list,robot)
    vertex = [mr.point_start, mr.point_goal]
    vertex.append((100,100))
    vertex.append((100,200))
    vertex,adj_matrix = mr.prm(vertex=vertex,show=True,n=110)
#简单环境的算法测试,能够很好的走另一条没有障碍物的路
def simple_test():
    img,crowd_list,robot = world_8()
    mr = DE2(img,crowd_list,robot)
    vertex = [mr.point_start, mr.point_goal]
    vertex.append((100,100))
    vertex.append((100,200))
    vertex.append((200,150))
    vertex.append((310,13))
    print("~~~~~~~~~old way~~~~~~~~~~~~")
    sign1,path1,img = super(DE2,mr).prm_planning(vertex=vertex,show=True,n=400)
    print("~~~~~~~~~new way~~~~~~~~~~~~")
    sign2,path2,img2 = mr.prm_planning(vertex=vertex,show=True,n=400)
    if path1:
        print("path1=",path1)
    if path2:
        print("path2=",path2)
    if sign1:
        cv2.imshow("oldway",img)
    if sign2:
        cv2.imshow("newway",img2)
    cv2.waitKeyEx(0)
    return mr,sign1,path1,img,sign2,path2,img2
#world8 test testOK 发现没有必要把D_max调那么大,只要一点点就可以知道线附近的情况
# D_MAX:  8 7 6 ->2 * CIRCLE_R 5 4 3 2 1 0 ->8 * CIRCLE_R 否则会走人多的路 ----那么其实D_MAX=8 * CIRCLE_R即可
def world_PRM(img,crowd_list,robot,D_MAX):
    mr = DE2(img,crowd_list,robot)
    mr.D_max = D_MAX
    sign1,path1,img = super(DE2,mr).prm_planning(s=50,n=200)
    sign2,path2,img2 = mr.prm_planning(s=50,n=200)
    return mr,sign1,path1,img,sign2,path2,img2
#--------------------------------------------------------------
def PRM_A_START_APF(DE2,foldname,path,img,
                    PRM_POINT_NUM = 20,
                    PRM_DISTANCE = 200):
    #一些状态的初始化以及环境的初始化
    step_num = 0
    collision_time = 0
    reward = 0
    DE2.reset()
    #显示一下PRM和A*的成果
    cv2.imwrite(foldname + "prm_planning.jpg", img)
    #打印出得到的路径
    print(path)
    k = len(path) - 2
    #从第一个局部目标点开始导航
    DE2.point_goal=DE2.vertex[path[k]]
    print("game begin")
    for i in range(300):#最多循环三百个step
        img = DE2.render()
        img = visualize_apf(img,DE2,reward)
        cv2.imwrite(foldname+"img"+str(i)+".jpg",img)
        observation,reward, done,info = DE2.step(DE2.apf_next_guide(DE2.Robot.getLocation(),DE2.vertex[path[k]]))
        step_num += 1
        # detect whether have a collision or reach local goal
        if reward == COLLISION_REWARD:
            collision_time += 1
            print("collision!",collision_time)
        if reward == REACH_GOAL_REWARD :
            k -= 1
            # if k == -1 than reach the end
            if k == -1:
                break
            # or reach the local goal ,keep going
            print("reach local goal", k)
            DE2.point_goal = DE2.vertex[path[k]]
            DE2.reward-=REACH_GOAL_REWARD
        if collision_time>30:
            break
    #保存setting_and_result.yaml
    py_object={
        'Reward':DE2.reward,
        'Step_num':step_num,
        'Collision_time':collision_time,
        'PRM_POINT_NUM':PRM_POINT_NUM,
        'PRM_DISTANCE':PRM_DISTANCE,
        'APF_WAY':DE2.APF_WAY,
        'route':DE2.Robot.getRoute()
    }
    generate_yaml_doc(foldname+"setting_and_result.yaml",py_object)
    #保存my_motion_planning_toolbox.yaml
    py_object = {"D_MAX": D_MAX,
                 "OBSTACLE_MAX": OBSTACLE_MAX,
                 "APF_WAY": DE2.APF_WAY,
                 "ROU": ROU}
    generate_yaml_doc(foldname+"my_motion_planning_toolbox.yaml", py_object)
    #保存my_motion_roadmap.yaml
    generate_yaml_doc(foldname+"my_motion_roadmap.yaml", data)
def NO_VISIUAL_PRM_A_START_APF(DE2,foldname,path,img,
                    PRM_POINT_NUM = 20,
                    PRM_DISTANCE = 200):
    #一些状态的初始化以及环境的初始化
    step_num = 0
    collision_time = 0
    DE2.reset()
    #显示一下PRM和A*的成果
    cv2.imwrite(foldname + "/prm_planning.jpg", img)
    #打印出得到的路径
    print(path)
    k = len(path) - 2
    #从第一个局部目标点开始导航
    DE2.point_goal=DE2.vertex[path[k]]
    print("game begin")
    for i in range(300):#最多循环三百个step
        observation,reward, done,info = DE2.step(DE2.apf_next_guide(DE2.Robot.getLocation(),DE2.vertex[path[k]]))
        step_num += 1
        # detect whether have a collision or reach local goal
        if reward == COLLISION_REWARD:
            collision_time += 1
            print("collision!",collision_time)
        if reward == REACH_GOAL_REWARD :
            k -= 1
            # if k == -1 than reach the end
            if k == -1:
                break
            # or reach the local goal ,keep going
            print("reach local goal", k)
            DE2.point_goal = DE2.vertex[path[k]]
            DE2.reward-=REACH_GOAL_REWARD
        if collision_time>30:
            break
    #保存setting_and_result.yaml
    py_object={
        'Reward':DE2.reward,
        'Step_num':step_num,
        'Collision_time':collision_time,
        'PRM_POINT_NUM':PRM_POINT_NUM,
        'PRM_DISTANCE':PRM_DISTANCE,
        'APF_WAY':DE2.APF_WAY,
        'route':DE2.Robot.getRoute()
    }
    generate_yaml_doc(foldname+"setting_and_result.yaml",py_object)
    #保存my_motion_planning_toolbox.yaml
    py_object = {"D_MAX": D_MAX,
                 "OBSTACLE_MAX": OBSTACLE_MAX,
                 "APF_WAY": DE2.APF_WAY,
                 "ROU": ROU}
    generate_yaml_doc(foldname+"my_motion_planning_toolbox.yaml", py_object)
    #保存my_motion_roadmap.yaml
    generate_yaml_doc(foldname+"my_motion_roadmap.yaml", data)
#世界对象,A*成功标志位,A*Path,A*规划图片;改进的A*成功标志位,改进的A*Path,改进的A*规划图片
def temp_world_function(world_num,img,crowd_list,robot):
    MY_D_MAX = 8 * CIRCLE_R
    de2,sign1,path1,img,sign2,path2,img2 = world_PRM(img,crowd_list,robot,MY_D_MAX)
    for i in range(4):
        de2.APF_WAY = i
        if sign1:
            NO_VISIUAL_PRM_A_START_APF(DE2=de2, foldname="animFram/Astar/APFWAY"+str(i)+"/"+str(world_num)+"/", path=path1, img=img)
        if sign2:
            NO_VISIUAL_PRM_A_START_APF(DE2=de2, foldname="animFram/impovedAstar/APFWAY"+str(i)+"/"+str(world_num)+"/", path=path2, img=img2)
# img,crowd_list,robot = world_0()
# temp_world_function(0,img,crowd_list,robot)
# img,crowd_list,robot = world_1()
# temp_world_function(1,img,crowd_list,robot)
# img,crowd_list,robot = world_2()
# temp_world_function(2,img,crowd_list,robot)
# img,crowd_list,robot = world_3()
# temp_world_function(3,img,crowd_list,robot)
# img,crowd_list,robot = world_4()
# temp_world_function(4,img,crowd_list,robot)
# img,crowd_list,robot = world_5()
# temp_world_function(5,img,crowd_list,robot)
# img,crowd_list,robot = world_6()
# temp_world_function(6,img,crowd_list,robot)
# img,crowd_list,robot = world_7()
# temp_world_function(7,img,crowd_list,robot)
# img,crowd_list,robot = world_8()
# temp_world_function(8,img,crowd_list,robot)
# prelocation = "animFram/paperdata/"
# AstartLocation = "/Astar/APFWAY"
# imProved_AstartLocation = "/impovedAstar/APFWAY"
# record=np.ones((7,2,4,8,2))
# for i in range(1,7):
#     for j in range(4):
#         for k in range(8):
#             for index,l in enumerate([AstartLocation, imProved_AstartLocation]):
#                 if k == 7:
#                     location = prelocation + str(i) + l + str(j) + "/" + str(k+1)
#                 else:
#                     location = prelocation + str(i) + l + str(j) + "/" + str(k)
#                 result_location = os.path.join(location, "setting_and_result.yaml")
#                 file = open(result_location, 'r', encoding="utf-8")
#                 file_data = file.read()
#                 file.close()
#                 result = yaml.load(file_data)
#                 record[i-1][index][j][k][0] = result['Collision_time']
#                 record[i-1][index][j][k][1] = result['Step_num']
# np.save("A.npy",record)


# B=np.load("A.npy")
# print(B)

#查看
img,crowd_list,robot = world_8()
mr = DE2(img,crowd_list,robot)
img = mr.world_distribution(show=True)
cv2.imwrite("DE2_world8.bmp",img)
