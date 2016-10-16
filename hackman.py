#!/usr/bin/env python3

from random import randrange, choice, shuffle, randint, seed, random
from math import cos, pi, sin, sqrt, atan

from fractions import Fraction
import operator
from game import Game
from copy import deepcopy

import player

try:
    from sys import maxint
except ImportError:
    from sys import maxsize as maxint

LAND = -2
WATER = -1
MAP_OBJECT = '.%'

PLAYER1 = 0
PLAYER2 = 1
BUG = 2
WEAPON = 3
CODE = 4

VALID_ORDERS = ["up", "down", "left", "right", "pass"]

ADJACENT = [
    (-1, 0),
    (0, 1),
    (1, 0),
    (0, -1)
]

class Hackman(Game):
    def __init__(self, options=None):
        self.width = 0
        self.height = 0
        self.cutoff = None
        map_text = options['map']
#        self.turns = int(options['turns'])
#        self.loadtime = int(options['loadtime'])
#        self.turntime = int(options['turntime'])
        self.timebank = 0
        if 'timebank' in options:
            self.timebank = int(options['timebank'])
        self.time_per_move = int(options['time_per_move'])
        self.player_names = ["player0", "player1"] #options['player_names']
        self.engine_seed = options.get('engine_seed',
            randint(-maxint-1, maxint))
        self.player_seed = options.get('player_seed',
            randint(-maxint-1, maxint))

        seed(self.engine_seed)
        self.turn = 0
        self.turn_limit = int(options['turns'])
        self.num_players = 2 # map_data["players"]
        self.players = [player.Player(), player.Player()]
        self.player_to_begin = randint(0, self.num_players)
        # used to cutoff games early
        self.cutoff_turns = 0
        # used to calculate the turn when the winner took the lead
        self.winning_bot = None
        self.winning_turn = 0
        # used to calculate when the player rank last changed
        self.ranking_bots = None
        self.ranking_turn = 0

        # initialize scores
        self.score = [0]*self.num_players
        self.bonus = [0]*self.num_players
        self.score_history = [[s] for s in self.score]

        # used to track dead players
        self.killed = [False for _ in range(self.num_players)]

        # used to give a different ordering of players to each player;
        # initialized to ensure that each player thinks they are player 0
        # Not used in this game I think.
        self.switch = [[None]*self.num_players + list(range(-5,0))
                       for i in range(self.num_players)]
        for i in range(self.num_players):
            self.switch[i][i] = 0

        # the engine may kill players before the game starts and this is needed
        # to prevent errors
        self.orders = [[] for i in range(self.num_players)]

        ### collect turns for the replay
        self.replay_data = []

        self.server = []    # server room locations
        self.map_data = self.parse_map(map_text)

    def string_cell_item(self, item):
        if item == PLAYER1:
            return '0'
        elif item == PLAYER2:
            return '1'
        elif item == BUG:
            return 'E'
        elif item == WEAPON:
            return 'W'
        elif item == CODE:
            return 'C'
        else:
            return ''

    def in_bounds (self, row, col):
        return row > 0 and col > 0 and col < self.width and row < self.height

    def output_cell (self, cell):
        if len(cell) == 0:
            return '.'
        elif WATER in cell:
            return 'x'
        else:
            result = ""
            for item in cell:
                result += self.string_cell_item(item)
            return result

    def string_field (self, field):
        flat = []
        for row in field:
            for cell in row:
                flat.append(cell)
        return (','.join([self.output_cell (cell) for cell in flat]))

    def init_grid (self, rows, cols):
        result = []
        for r in range(0, rows):
            result.append([])
            for c in range(0, cols):
                result[r].append([])
        return result
                

    def parse_map(self, map_text):
        """ Parse the map_text into a more friendly data structure """
        cols = None
        rows = None
        agents_per_player = None
        agents = []
        num_players = None
        count_row = 0
        grid = [[]]
        for line in map_text.split("\n"):
            line = line.strip()

            # ignore blank lines and comments
            if not line or line[0] == "#":
                continue

            key, value = line.split(" ", 1)
            key = key.lower()

            if key == "cols":
                cols = int(value)
                self.width = cols
                if rows != None:
                    grid = self.init_grid(rows, cols)
            elif key == "rows":
                rows = int(value)
                self.height = rows
                if cols != None:
                    grid = self.init_grid(rows, cols)

            elif key == 'p':
                loc = value.split()
                p_num = int(loc[0])
                p_row = int(loc[1])
                p_col = int(loc[2])
                self.players[p_num].row = p_row
                self.players[p_num].col = p_col
                grid[p_row][p_col].append(p_num)

            elif key == 'm':
                if len(value) != cols:
                    raise Exception("map",
                                    "Incorrect number of cols in row %s. "
                                    "Got %s, expected %s."
                                    %(row, len(value), width))
                for count_col, c in enumerate(value):
                    if c == MAP_OBJECT[WATER]:
#                        print("len grid = " + str(len (grid)))
#                        print("len grid[0] = " + str(len (grid[0])))
                        grid[count_row][count_col].append(WATER)
#                    elif c == MAP_OBJECT[LAND]:
#                        grid[count_row][count_col].append(LAND)
                    elif c not in MAP_OBJECT:
                        raise Exception("map",
                                        "Invalid character in map: %s" % c)
                count_row += 1

            elif key == 's':    # server room
                loc = value.split()
                p_row = int(loc[0])
                p_col = int(loc[1])
                self.server.append((p_row, p_col))

        if count_row != rows:
                    raise Exception("map",
                                    "Incorrect number of rows in map "
                                    "Got %s, expected %s."
                                    %(count_row, rows))
        self.field = grid
        return {
            "size": (rows, cols),
            "grid" : grid }

    def render_changes(self, player, time_to_move):
        """ Create a string which communicates the updates to the state
        """
        updates = self.get_state_changes(time_to_move)
        visible_updates = []
        # next list all transient objects
        for update in updates:
            visible_updates.append(update)
        visible_updates.append([]) # newline
        return '\n'.join(' '.join(map(str,s)) for s in visible_updates)

    def get_state_changes(self, time_to_move):
        """ Return a list of all transient objects on the map.

        """
        changes = []
        changes.extend([['update game round', self.turn + 1]])
        changes.extend([['update game field', self.string_field(self.field)]])
        changes.extend([['update player0 snippets', self.players[0].snippets]])
        changes.extend([['update player0 has_weapon', self.players[0].has_weapon]])
        changes.extend([['update player0 is_paralyzed', self.players[0].is_paralyzed]])
        changes.extend([['update player1 snippets', self.players[1].snippets]])
        changes.extend([['update player1 has_weapon', self.players[1].has_weapon]])
        changes.extend([['update player1 is_paralyzed', self.players[1].is_paralyzed]])
        changes.extend([['action move', int(time_to_move * 1000)]]) 
        return changes

    def convert_move(self, move):
        """ Convert text string to co-ordinate offset
        """
        if move == "up":
            return {"row" : -1, "col" : 0}
        elif move == "down":
            return {"row": 1, "col" : 0}
        elif move == "left":
            return {"row": 0, "col" : -1}
        elif move == "right":
            return {"row": 0, "col" : 1}
        elif move == "pass":
            return None
        else:
            raise ValueError("Failed to convert string to move: " + move)

    def parse_orders(self, player, lines):
        """ Parse orders from the given player
        player is an integer
        """
        orders = []
        valid = []
        ignored = []
        invalid = []

        for line in lines:
            line = line.strip().lower()
            # ignore blank lines and comments
            if not line: # or line[0] == '#':
                continue

            if line[0] == '#':
                ignored.append((line))
                continue

            data = line.split()

            try:

                # validate data format
                if data[0] not in VALID_ORDERS:
                    invalid.append((line, 'unknown action'))
                    continue
                else:
                    move = self.convert_move(data[0])
                if move:
                    row, col = self.players[player].row + move['row'], self.players[player].col + move['col']
                    orders.append((player, row, col))

                valid.append(line)

            except ValueError:
                invalid.append((line, "submitted move is invalid: " + line))
                continue

        return orders, valid, ignored, invalid



    def bots_to_play(self, turn):
        """ Indices of the bots who should receive the game state and return orders now """
        return [0, 1]

    def board_symbol(self, cell):
        if cell == PLAYER1:
            return '0'
        elif cell == PLAYER2:
            return '1'
        elif cell == BUG:
            return 'E'
        elif cell == WEAPON:
            return 'W'
        elif cell == CODE:
            return 'C'
        elif cell == LAND:
            return '.'
        elif cell == WATER:
            return 'x'
        else:
            raise ValueError ("Invalid board_symbol: " + cell)

    def text_board(self):
        count = 0
        print ("\n")
        output = ""
        for cell in self.field:
            if count >= field_size:
                print(output)
                output=""
                count = 0
            if len(cell) > 0:
                output += self.board_symbol(cell[0])
            else:
                output += self.board_symbol(LAND)
            count += 1
        print(output)

    def player_cell (self, player):
        if player == 0: return PLAYER1 
        else: return PLAYER2

    def adjacent_coords (self, row, col):
        result = []
        for (orow, ocol) in ADJACENT:
            (trow, tcol) = (row + orow, col + ocol)
            if self.in_bounds (trow, tcol):
                result.append((trow, tcol))
        return result

    def is_legal(self, player, row, col):
        in_range = (row, col) in self.adjacent_coords(self.players[player].row, self.players[player].col)
        not_blocked = (WATER not in self.field[row][col])
        return in_range and not_blocked

    def place_move(self, move):
        (player, row, col) = move
        p = self.players[player]
        if self.is_legal (player, row, col):
            self.field[p.row][p.col].remove(self.player_cell(player))
            self.field[row][col].append(self.player_cell(player))
            p.row = row
            p.col = col

    def do_orders(self):
        """ Execute player orders and handle conflicts
        """
        for player in self.bots_to_play(self.turn):
            if self.is_alive(player):
                if len(self.orders[player]) > 0:
                    self.place_move (self.orders[player][0])
            else:
                pass
        self.resolve_interactions()

    def resolve_interactions(self):
        pass
    # Common functions for all games

    def game_over(self):
        """ Determine if the game is over

            Used by the engine to determine when to finish the game.
            A game is over when there are no players remaining, or a single
              winner remaining.
        """
        if len(self.remaining_players()) < 1:
            self.cutoff = 'extermination'
            return True
        elif len(self.remaining_players()) == 1:
            self.cutoff = 'lone survivor'
            return True
        elif self.turn >= self.turn_limit:
            self.cutoff = 'turn limit reached'
            return True
        else: return False

    def kill_player(self, player):
        """ Used by engine to signal that a player is out of the game """
        print("Player killed: " + str(player))
        self.killed[player] = True
        self.players[player].snippets = -1

    def start_game(self):
        """ Called by engine at the start of the game """
        self.game_started = True
        
        ### append turn 0 to replay
        self.replay_data.append( self.get_state_changes(self.time_per_move) )
        result = []

    def score_game(self):
            return [self.players[0].snippets, self.players[1].snippets]

    def finish_game(self):
        """ Called by engine at the end of the game """

        self.score = self.score_game()
#        self.text_board()
#        self.text_macroboard()
        self.calc_significant_turns()
        for i, s in enumerate(self.score):
            self.score_history[i].append(s)
        self.replay_data.append( self.get_state_changes(self.time_per_move) )

        # check if a rule change lengthens games needlessly
        if self.cutoff is None:
            self.cutoff = 'turn limit reached'

    def start_turn(self):
        """ Called by engine at the start of the turn """
        self.turn += 1
#        self.text_board()
#        self.text_macroboard()
        self.orders = [[] for _ in range(self.num_players)]

    def finish_turn(self):
        """ Called by engine at the end of the turn """
        self.do_orders()
        # record score in score history
        for i, s in enumerate(self.score):
            if self.is_alive(i):
                self.score_history[i].append(s)
            elif s != self.score_history[i][-1]:
                # score has changed, increase history length to proper amount
                last_score = self.score_history[i][-1]
                score_len = len(self.score_history[i])
                self.score_history[i].extend([last_score]*(self.turn-score_len))
                self.score_history[i].append(s)
        self.calc_significant_turns()
#        self.update_scores()

        ### append turn to replay
        self.replay_data.append( self.get_state_changes(self.time_per_move) )

    def calc_significant_turns(self):
        ranking_bots = [sorted(self.score, reverse=True).index(x) for x in self.score]
        if self.ranking_bots != ranking_bots:
            self.ranking_turn = self.turn
        self.ranking_bots = ranking_bots

        winning_bot = [p for p in range(len(self.score)) if self.score[p] == max(self.score)]
        if self.winning_bot != winning_bot:
            self.winning_turn = self.turn
        self.winning_bot = winning_bot

    def get_state(self):
        """ Get all state changes

            Used by engine for streaming playback
        """
        updates = self.get_state_changes()
        updates.append([]) # newline
        return '\n'.join(' '.join(map(str,s)) for s in updates)

    def get_player_start(self, player=None):
        """ Get game parameters visible to players

            Used by engine to send bots startup info on turn 0
        """
        result = []
        result.append(['settings player_names', ','.join(self.player_names)])
        result.append(['settings your_bot', self.player_names[player]])
        result.append(['settings timebank', self.timebank])
        result.append(['settings time_per_move', self.time_per_move])
        result.append(['settings your_botid', player])
        result.append(['settings field_width', self.width])
        result.append(['settings field_height', self.height])
        result.append(['settings max_rounds', self.turn_limit])

        result.append(['settings player_seed', self.player_seed])
        #result.append(['settings num_players', self.num_players])
        #message = self.get_player_state(player, self.timebank)

        result.append([]) # newline
        pen = '\n'.join(' '.join(map(str,s)) for s in result)
        return pen #+ message #+ 'ready\n'

    def get_player_state(self, player, time_to_move):
        """ Get state changes visible to player

            Used by engine to send state to bots
        """
        return self.render_changes(player, time_to_move)
    def is_alive(self, player):
        """ Determine if player is still alive

            Used by engine to determine players still in the game
        """
        if self.killed[player]:
            return False
        else:
            return True

    def get_error(self, player):
        """ Returns the reason a player was killed

            Used by engine to report the error that kicked a player
              from the game
        """
        return ''

    def do_moves(self, player, moves):
        """ Called by engine to deliver latest player orders """
        orders, valid, ignored, invalid = self.parse_orders(player, moves)
#        orders, valid, ignored, invalid = self.validate_orders(player, orders, valid, ignored, invalid)
        self.orders[player] = orders
        return valid, ['%s # %s' % ignore for ignore in ignored], ['%s # %s' % error for error in invalid]

    def get_scores(self, player=None):
        """ Gets the scores of all players

            Used by engine for ranking
        """
        #if player is None:
        return self.score
        #else:
        #    return self.order_for_player(player, self.score)

    def order_for_player(self, player, data):
        """ Orders a list of items for a players perspective of player #

            Used by engine for ending bot states
        """
        s = self.switch[player]
        return [None if i not in s else data[s.index(i)]
                for i in range(max(len(data),self.num_players))]

    def remaining_players(self):
        """ Return the players still alive """
        return [p for p in range(self.num_players) if self.is_alive(p)]

    def get_stats(self):
        """  Used by engine to report stats
        """
        stats = {}
        return stats

    def get_replay(self):
        """ Return a summary of the entire game

            Used by the engine to create a replay file which may be used
            to replay the game.
        """
        replay = {}
        # required params
        replay['revision'] = 1
        replay['players'] = self.num_players

        # optional params
        replay['loadtime'] = self.timebank
        replay['turntime'] = self.time_per_move
        replay['turns'] = self.turn
        replay['engine_seed'] = self.engine_seed
        replay['player_seed'] = self.player_seed

        # scores
        replay['scores'] = self.score_history
        replay['bonus'] = self.bonus
        replay['winning_turn'] = self.winning_turn
        replay['ranking_turn'] = self.ranking_turn
        replay['cutoff'] =  self.cutoff

        
        ### 
        replay['data'] = self.replay_data
        return replay


    def bot_input_finished(self, line):
        return line.strip().lower() in VALID_ORDERS

