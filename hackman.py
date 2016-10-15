#!/usr/bin/env python3

from random import randrange, choice, shuffle, randint, seed, random
from math import cos, pi, sin, sqrt, atan
from collections import deque, defaultdict

from fractions import Fraction
import operator
from game import Game
from copy import deepcopy

try:
    from sys import maxint
except ImportError:
    from sys import maxsize as maxint


EMPTY, PLAYER1, PLAYER2, ACTIVE, DRAW = (0, 1, 2, -1, 3)

field_size = 9
macroboard_size = 3

victory_lines = [
    ((0,0), (0, 1), (0, 2)),
    ((1,0), (1, 1), (1, 2)),
    ((2,0), (2, 1), (2, 2)),
    ((0,0), (1, 0), (2, 0)),
    ((0,1), (1, 1), (2, 1)),
    ((0,2), (1, 2), (2, 2)),
    ((0,0), (1, 1), (2, 2)),
    ((0,2), (1, 1), (2, 0))
]

class Uttt(Game):
    def __init__(self, options=None):
        self.cutoff = None
#        map_text = options['map']
#        self.turns = int(options['turns'])
#        self.loadtime = int(options['loadtime'])
#        self.turntime = int(options['turntime'])
        self.timebank = 0
        if 'timebank' in options:
            self.timebank = int(options['timebank'])
        self.time_per_move = int(options['time_per_move'])
        self.player_names = options['player_names']
        self.engine_seed = options.get('engine_seed',
            randint(-maxint-1, maxint))
        self.player_seed = options.get('player_seed',
            randint(-maxint-1, maxint))

        seed(self.engine_seed)
        self.field = [ EMPTY for j in range(0, field_size * field_size) ]
        self.macroboard = [ ACTIVE for j in range (0, macroboard_size * macroboard_size) ]

        self.turn = 0
        self.num_players = 2 # map_data["players"]
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

        # used to track dead players, ants may still exist, but orders are not processed # Ants?
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

    def output_cell (self, cell):
        if cell == DRAW: return str(EMPTY)
        else: return str(cell)

    def string_field (self, field):
        return ','.join([self.output_cell (cell) for cell in field])

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
        changes.extend([['update game round', int(self.turn / 2)]])
        changes.extend([['update game move', self.turn]])
        changes.extend([['update game macroboard', self.string_field(self.macroboard)]])
        changes.extend([['update game field', self.string_field(self.field)]])
        changes.extend([['action move', int(time_to_move * 1000)]]) 
        return changes
#        changes.extend(sorted(
#            ['p', p["player_id"]]
#            for p in self.players if self.is_alive(p["player_id"])))
#         changes.extend(sorted(
#             ['a', a["row"], a["col"], a["heading"], a["owner"]]
#             for a in self.agents))
#         changes.extend(sorted(
#             ['d', a["row"], a["col"], a["heading"], a["owner"]]
#             for a in self.killed_agents))
#         return changes

    def parse_orders(self, player, lines):
        """ Parse orders from the given player
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

            # validate data format
            if data[0] != 'place_move':
                invalid.append((line, 'unknown action'))
                continue
            else:
                col, row = data[1:]

            # validate the data types
            try:
                row, col = int(row), int(col)
                orders.append((player, row, col))
                valid.append(line)

            except ValueError:
                invalid.append((line, "row and col should be integers"))
                continue

        return orders, valid, ignored, invalid



    def bots_to_play(self, turn):
        """ Indices of the bots who should receive the game state and return orders now """
        if turn == 0: return [1, 0]
        else: return [(turn + 1) % 2]

    def board_symbol(self, cell):
        if cell == EMPTY:
            return ". "
        elif cell == ACTIVE:
            return "! "
        elif cell == PLAYER1:
            return "o "
        elif cell == PLAYER2:
            return "x "
        elif cell == DRAW:
            return "- "

    def text_board(self):
        count = 0
        print ("\n")
        output = ""
        for cell in self.field:
            if count >= field_size:
                print(output)
                output=""
                count = 0
            output += self.board_symbol(cell)
            count += 1
        print(output)

    def text_macroboard(self):
        count = 0
        print ("\n")
        output = ""
        for cell in self.macroboard:
            if count >= macroboard_size:
                print(output)
                output=""
                count = 0
            output += self.board_symbol(cell)
            count += 1
        print(output)
        print("")

    def player_cell (self, player):
        if player == 0: return PLAYER1 
        else: return PLAYER2

    def clear_active_macroboard(self):
        for count in range(0, len(self.macroboard)):
            if self.macroboard[count] == ACTIVE:
                self.macroboard[count] = EMPTY

    def get_board_cell (self, row, col):
        return self.field[int(row) * field_size + int(col)]

    def get_macroboard_cell (self, row, col):
        return self.macroboard[int(row) * macroboard_size + int(col)]

    def cell_is_full (self, row, col):
        offr = row * macroboard_size
        offc = col * macroboard_size
        result = True
        for cr in range(0, macroboard_size):
            for cc in range (0, macroboard_size):
                result = result and (self.get_board_cell(offr + cr, offc + cc) != EMPTY)
        return result

    def macroboard_full (self):
        result = True
        for cell in self.macroboard:
            if cell == EMPTY or cell == ACTIVE:
                result = False
        return result

    def macroboard_status (self):
        win = EMPTY
        for (r0, c0), (r1, c1), (r2, c2) in victory_lines:
            p0 = self.get_macroboard_cell(r0, c0)
            p1 = self.get_macroboard_cell(r1, c1)
            p2 = self.get_macroboard_cell(r2, c2)
            if p0 != EMPTY and p0 == p1 and p0 == p2:
                win = p0
        if win == EMPTY or win == ACTIVE:
            if self.macroboard_full():
                return DRAW
            else:
                return EMPTY
        else:
            return win
        
    def sub_board_status (self, row, col):
        offr = row * macroboard_size
        offc = col * macroboard_size
        win = EMPTY
        for (r0, c0), (r1, c1), (r2, c2) in victory_lines:
            p0 = self.get_board_cell(offr + r0, offc + c0)
            p1 = self.get_board_cell(offr + r1, offc + c1)
            p2 = self.get_board_cell(offr + r2, offc + c2)
            if p0 != EMPTY and p0 == p1 and p0 == p2:
                win = p0
        if win == EMPTY and self.cell_is_full(row, col):
            return DRAW
        else:
            return win
        
    
    def activate_all (self):
        for i, c in enumerate (self.macroboard):
            ir = int (i / macroboard_size)
            ic = i % macroboard_size
            if c == EMPTY and not self.cell_is_full(ir, ic):
                self.macroboard[i] = ACTIVE

    def count_active(self):
        result = 0;
        for i, c in enumerate (self.macroboard):
            if self.macroboard[i] == ACTIVE:
                result += 1
        return result

    def update_macroboard (self, row, col):
        self.clear_active_macroboard()
        ur = int(row / macroboard_size)
        uc = int(col / macroboard_size)
        self.macroboard[ur * macroboard_size + uc] = self.sub_board_status (ur, uc)
#        print("sub_board_status: " + str(self.sub_board_status (ur, uc)) + " " + str ((ur, uc)))
        mbr = row % macroboard_size
        mbc = col % macroboard_size
        if self.macroboard[mbr * macroboard_size + mbc] == EMPTY:
            #print ("Activating cell" + str((mbr, mbc)))
            self.macroboard[mbr * macroboard_size + mbc] = ACTIVE
        else:
            #print ("Activating all\n")
            self.activate_all()
        #print(self.string_field(self.macroboard) + "\n")

    def is_legal(self, row, col):
        mbr = int(row / macroboard_size)
        mbc = int(col / macroboard_size)
        return self.get_macroboard_cell (mbr, mbc) == ACTIVE and self.get_board_cell(row, col) == EMPTY

    def place_move(self, move):
        (player, row, col) = move
        #print("player = " + str(player))
        #print("player_cell = " + str(self.player_cell(player)))
        if self.is_legal (row, col):
            self.field[row * field_size + col] = self.player_cell(player)
            self.update_macroboard(row, col)

    def do_orders(self):
        """ Execute player orders and handle conflicts
        """
        player = self.bots_to_play(self.turn)[0]
        #print(str(self.orders))
        #print("player " + str(player))
        if self.is_alive(player):
            if len(self.orders[player]) > 0:
                self.place_move (self.orders[player][0])
        else:
            pass
#        player = self.bots_to_play()[0]
#        #print(str(self.orders))
#        #print("player " + str(player))
#        if self.is_alive(player):
##            if len(self.orders[player]) > 0:
#            for player_orders in self.orders:
#                for porder in player_orders:
#                    oplayer, row, col = porder
#                    if player == oplayer:
#                        print("place_move " + str(porder))
#                        self.place_move (porder)
#        else:
#            pass


    # Common functions for all games

    def game_won(self):
        return self.macroboard_status()

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
        elif self.game_won() == DRAW:
            self.cutoff = "Board full"
            return True
        elif self.game_won() != EMPTY:
            self.cutoff = "Game won"
            return True
        elif self.count_active() < 1:
            self.cutoff = "No more moves"
            return True
        else: return False

    def kill_player(self, player):
        """ Used by engine to signal that a player is out of the game """
        print("Player killed: " + str(player))
        self.killed[player] = True
        self.score[player] = -1

    def start_game(self):
        """ Called by engine at the start of the game """
        self.game_started = True
        
        ### append turn 0 to replay
        self.replay_data.append( self.get_state_changes(self.time_per_move) )
        result = []

    def score_game(self):
        result = self.macroboard_status()
        if self.score[0] < 0 or self.score[1] < 0:
            return self.score
        elif result == EMPTY or result == ACTIVE or result == DRAW:
            return [0, 0]
        elif result == PLAYER1:
            return [1, 0]
        elif result == PLAYER2:
            return [0, 1]
        else:
            return [0, 0]

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
        #original.process_new_fleets(self.planets, self.fleets, self.temp_fleets)
        #self.planets, self.fleets = original.do_time_step(self.planets, self.fleets)
        #self.score = [original.num_ships_for_player(self.planets, self.fleets, player) for player in (1, 2)]
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
        result.append(['settings timebank', self.timebank])
        result.append(['settings time_per_move', self.time_per_move])
        result.append(['settings your_botid', player + 1])
        result.append(['settings player_names', ','.join(self.player_names)])
        result.append(['settings player_seed', self.player_seed])
        result.append(['settings num_players', self.num_players])
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
        """ Called by engine to give latest player orders """
        orders, valid, ignored, invalid = self.parse_orders(player, moves)
#        orders, valid, ignored, invalid = self.validate_orders(player, orders, valid, ignored, invalid)
        self.orders[player] = orders
        return valid, ['%s # %s' % ignore for ignore in ignored], ['%s # %s' % error for error in invalid]

    def get_scores(self, player=None):
        """ Gets the scores of all players

            Used by engine for ranking
        """
        if player is None:
            return self.score
        else:
            return self.order_for_player(player, self.score)

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
        return line.lower().startswith('place_move')

