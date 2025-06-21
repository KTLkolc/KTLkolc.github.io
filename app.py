import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from uuid import uuid4
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
socketio = SocketIO(app, cors_allowed_origins="*")

# 内存中存储房间数据 (生产环境应使用数据库)
rooms = {}
players = {}

class Room:
    def __init__(self, name, max_players, password=None, game_mode="classic"):
        self.id = str(uuid4())
        self.name = name
        self.max_players = max_players
        self.password = password
        self.game_mode = game_mode
        self.players = []
        self.status = "waiting"  # waiting, playing, ended
        self.created_at = datetime.now()
        self.game_state = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/rooms', methods=['GET'])
def list_rooms():
    """获取可用房间列表"""
    public_rooms = [{
        'id': room.id,
        'name': room.name,
        'game_mode': room.game_mode,
        'current_players': len(room.players),
        'max_players': room.max_players,
        'has_password': room.password is not None,
        'status': room.status
    } for room in rooms.values() if room.status == "waiting"]
    
    return jsonify(public_rooms)

@app.route('/api/rooms', methods=['POST'])
def create_room():
    """创建新房间"""
    data = request.json
    name = data.get('name')
    max_players = int(data.get('max_players', 2))
    password = data.get('password')
    game_mode = data.get('game_mode', 'classic')
    
    if not name:
        return jsonify({'error': '房间名称不能为空'}), 400
    
    room = Room(name, max_players, password, game_mode)
    rooms[room.id] = room
    
    return jsonify({
        'room_id': room.id,
        'name': room.name,
        'max_players': room.max_players,
        'has_password': room.password is not None
    })

@socketio.on('connect')
def handle_connect():
    """客户端连接事件"""
    print(f"客户端已连接: {request.sid}")

@socketio.on('join_room')
def handle_join_room(data):
    """加入房间"""
    room_id = data.get('room_id')
    player_name = data.get('player_name', f"玩家-{request.sid[:4]}")
    password = data.get('password')
    
    if room_id not in rooms:
        emit('error', {'message': '房间不存在'})
        return
    
    room = rooms[room_id]
    
    # 验证密码
    if room.password and room.password != password:
        emit('error', {'message': '房间密码错误'})
        return
    
    # 检查房间是否已满
    if len(room.players) >= room.max_players:
        emit('error', {'message': '房间已满'})
        return
    
    # 加入房间
    join_room(room_id)
    player = {
        'id': request.sid,
        'name': player_name,
        'ready': False
    }
    room.players.append(player)
    players[request.sid] = {'room_id': room_id, 'player': player}
    
    # 通知房间内所有玩家
    emit('player_joined', {
        'player': player,
        'room_info': get_room_info(room)
    }, room=room_id)
    
    # 发送给当前玩家
    emit('room_joined', {
        'room': get_room_info(room),
        'players': room.players
    })

@socketio.on('leave_room')
def handle_leave_room():
    """离开房间"""
    if request.sid not in players:
        return
    
    player_data = players[request.sid]
    room_id = player_data['room_id']
    player = player_data['player']
    
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    room.players = [p for p in room.players if p['id'] != request.sid]
    
    leave_room(room_id)
    del players[request.sid]
    
    # 通知房间内其他玩家
    emit('player_left', {
        'player_id': request.sid,
        'room_info': get_room_info(room)
    }, room=room_id)
    
    # 如果房间为空，删除房间
    if len(room.players) == 0:
        del rooms[room_id]

@socketio.on('toggle_ready')
def handle_toggle_ready():
    """切换准备状态"""
    if request.sid not in players:
        return
    
    player_data = players[request.sid]
    room_id = player_data['room_id']
    player = player_data['player']
    
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    player['ready'] = not player['ready']
    
    # 通知房间内所有玩家
    emit('player_ready', {
        'player_id': request.sid,
        'is_ready': player['ready'],
        'room_info': get_room_info(room)
    }, room=room_id)
    
    # 检查是否所有玩家都准备就绪
    if all(p['ready'] for p in room.players) and len(room.players) >= 2:
        start_game(room_id)

def start_game(room_id):
    """开始游戏"""
    if room_id not in rooms:
        return
    
    room = rooms[room_id]
    room.status = "playing"
    
    # 初始化游戏状态 (根据游戏逻辑自定义)
    room.game_state = {
        'turn': 0,
        'current_player': room.players[0]['id'],
        'board': initialize_game_board(room.game_mode)
    }
    
    # 通知房间内所有玩家
    emit('game_started', {
        'game_state': room.game_state
    }, room=room_id)

def initialize_game_board(game_mode):
    """根据游戏模式初始化游戏棋盘"""
    # 这里根据您的游戏逻辑实现
    if game_mode == "classic":
        return {"type": "classic", "state": "initial"}
    elif game_mode == "team":
        return {"type": "team", "state": "initial"}
    else:
        return {"type": "custom", "state": "initial"}

def get_room_info(room):
    """获取房间信息"""
    return {
        'id': room.id,
        'name': room.name,
        'game_mode': room.game_mode,
        'current_players': len(room.players),
        'max_players': room.max_players,
        'status': room.status
    }

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
