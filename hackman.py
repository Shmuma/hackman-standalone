#!/usr/bin/env python3

from math import cos, pi, sin, sqrt, atan
import sys

import random

from fractions import Fraction
import operator
from game import Game
from copy import deepcopy

import player
import bug

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

CODE_SPAWN_DELAY = 8
WEAPON_SPAWN_DELAY = 20
BUG_SPAWN_COUNT = 5
HIT_PENALTY = 4

class Hackman(Game):
    def __init__(self, options=None):
        self.width = 0
        self.height = 0
        self.cutoff = None
        map_text = options['map']
#        self.turns = int(options['turns'])
#        self.loadtime = int(options['loadtime'])
#        self.turntime = int(options['turntime'])
        self.engine_seed = options.get('engine_seed',
            random.randint(-maxint-1, maxint))
        random.seed(self.engine_seed)
        self.timebank = 0
        if 'timebank' in options:
            self.timebank = int(options['timebank'])
        self.time_per_move = int(options['time_per_move'])
        self.player_names = ["player0", "player1"] #options['player_names']
        self.player_seed = options.get('player_seed',
            random.randint(-maxint-1, maxint))

        self.turn = 0
        self.turn_limit = int(options['turns'])
        self.num_players = 2 # map_data["players"]
        self.players = [player.Player(), player.Player()]
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
        self.bugs = []
        self.snippets_collected = 0
        self.map_data = self.parse_map(map_text)

        self.spawn_snippet()
        self.spawn_snippet()

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
        if PLAYER1 in cell:
            return '0'
        elif PLAYER2 in cell:
            return '1'
        elif BUG in cell:
            return 'E'
        elif WEAPON in cell:
            return 'W'
        elif CODE in cell:
            return 'C'
        elif LAND in cell:
            return '.'
        elif WATER in cell:
            return 'x'
        elif len(cell) == 0:
            return '.'
        else:
            raise ValueError ("Invalid board_symbol: " + str(cell))

    def text_board(self):
        print ("\n")
        for row in self.field:
            print("")
            for cell in row:
                sys.stdout.write(self.board_symbol(cell))
        print("\n")

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

    def remove_snippets(self, row, col):
        self.field[row][col] = [x for x in self.field[row][col] if x != CODE]

    def remove_sword(self, row, col):
        result = []
        removed = False
        for item in self.field[row][col]:
            if item == WEAPON and not removed:
                removed = True
            else:
                result.append(item)
        self.field[row][col] = result

    def remove_cell_bug(self, row, col):
        result = []
        removed = False
        for item in self.field[row][col]:
            if item == BUG and not removed:
                removed = True
            else:
                result.append(item)
        self.field[row][col] = result

    def remove_list_bug(self, row, col):
        removed = False
        result = []
        for bug in self.bugs:
            if (not removed) and bug.row == row and bug.col == col:
                removed = True
            else:
                result.append(bug)
        self.bugs = result

    def remove_list_bugs(self, row, col):
        result = []
        for bug in self.bugs:
            if bug.row == row and bug.col == col:
                removed = True
            else:
                result.append(bug)
        self.bugs = result

    def remove_bug(self, row, col):
        self.remove_cell_bug(row, col)
        self.remove_list_bug(row, col)

    def random_empty_cell(self):
        empty = []
        for (ir, row) in enumerate(self.field):
            for (ic, cell) in enumerate(row):
                if len(cell) == 0:
                    empty.append((ir, ic))
        if len(empty) > 0:
            return random.choice(empty)
        else:
            return None

    def spawn_snippet(self):
        chosen = self.random_empty_cell()
        if chosen:
            (row, col) = chosen
            self.field[row][col].append(CODE)

    def spawn_weapon(self):
        chosen = self.random_empty_cell()
        if chosen:
            (row, col) = chosen
            self.field[row][col].append(WEAPON)

    def spawn_bug(self):
        if len(self.server) > 0:
            chosen = random.choice(self.server)
            (row, col) = chosen
            newbug = bug.Bug()
            newbug.row = row
            newbug.col = col
            newbug.dir = random.randint(0, 3)
            newbug.prev_row = row
            newbug,prev_col = col
            self.bugs.append(newbug)
            self.field[row][col].append(BUG)

    def players_in_cell(self, cell):
        result = []
        for item in cell:
            if ((item == PLAYER1) or (item == PLAYER2)) and (item not in result):
                result.append(item)
        return result

    def bugs_in_cell(self, cell):
        result = 0
        for item in cell:
            if item == BUG:
                result += 1
        return result

    def snippets_in_cell(self, cell):
        result = 0
        for item in cell:
            if item == CODE:
                result += 1
        return result

    def swords_in_cell(self, cell):
        result = 0
        for item in cell:
            if item == WEAPON:
                result += 1
        return result

    def award_snippets(self, player, number):
        self.players[player].has_collected = True
        self.players[player].snippets += number
        self.snippets_collected += number
        sys.stderr.write(str(number) + " snippet(s) picked up by player" + str(player) + ", score is " + str(self.players[player].snippets) + "\n")
        while self.snippets_collected >= BUG_SPAWN_COUNT:
            self.snippets_collected -= BUG_SPAWN_COUNT
            self.spawn_bug()

    def award_sword(self, player):
        self.players[player].has_weapon = True
        sys.stderr.write("Sword picked up by player" + str(player) + "\n")

    def players_with_swords(self, players):
        result = 0
        for player in players:
            p = self.players[player]
            if p.has_weapon:
                result += 1
        return result

    def collide_bugs(self, player, bugs):
        p = self.players[player]
        if p.has_weapon:
            sys.stderr.write("player" + str(player) + " hits bug with weapon.\n")
            p.has_weapon = False
#        elif p.has_collected:
        else:
            sys.stderr.write("player" + str(player) + " hit by bug.\n")
            p.snippets -= HIT_PENALTY
            sys.stderr.write("player" + str(player) + " score is " + str(p.snippets) + "\n")
            if p.snippets < 0:
                self.kill_player(player)
    
    def remove_bugs(self, row, col):
        self.field[row][col] = [x for x in self.field[row][col] if x != BUG]
        remove_list_bugs(row, col)

    def interact(self, cell, row, col):
        cell_players = self.players_in_cell(cell)
#        sys.stderr.write(str(cell) + "\n")
#        sys.stderr.write(str(cell_players) + "\n")
        cell_bugs = self.bugs_in_cell(cell)
        cell_snippets = self.snippets_in_cell(cell)
        cell_swords = self.swords_in_cell(cell)
        if len(cell_players) > 0:
#            sys.stderr.write("interacting with player\n")
            if cell_bugs > 0:
                bug_killed = min (1, self.players_with_swords(cell_players))
                for player in cell_players:
                    self.collide_bugs(player, cell_bugs)
                if bug_killed > 0:
                    sys.stderr.write("One bug removed with sword\n")
                    self.remove_bug(row, col)
                self.remove_bugs(row, col)
            if cell_snippets > 0:
                num_players = len(cell_players)
#                sys.stderr.write("Player and snippet found in same cell\n")
                if num_players > 1:
                    for snippet in range(1, cell_snippets):
                        chosen = random.choice(cell_players)
                        self.award_snippets(chosen, 1)
                else:
                    self.award_snippets(cell_players[0], cell_snippets)
                self.remove_snippets(row, col)
            if cell_swords > 0:
                num_players = len(cell_players)
#                sys.stderr.write("Player and snippet found in same cell\n")
                if num_players > 1:
                    for sword in range(1, cell_swords):
                        chosen = random.choice(cell_players)
                        self.award_sword(chosen)
                        self.remove_sword(row, col)
                else:
                    self.award_sword(cell_players[0])
                
    def remove_specific_bug(self, bug): # FIXME duplicating logic because too sleepy to think
        self.bugs = [b for b in self.bugs if not (b === bug)
        tile_items = []
        removed = False
        for item in self.field[bug.row][bug.col]:
            if not removed and item == BUG:
                removed = True
            else:
                tile_items.append(item)
        self.field[bug.row][bug.col] = tile_items

    def swap_places_interact(self):
        for pnum, player in enumerate(self.players):
            bugs_swapped = self.get_bugs_swapped(player)
            if len(bugs_swapped) > 0:
                num_bugs = len(bugs_swapped)
                collide_bugs(pnum, num_bugs)
            for bug in bugs_swapped:
                self.remove_specific_bug(bug)
                    

    def resolve_interactions(self):
        self.swap_places_interact()
        for (ir, row) in enumerate(self.field):
            for (ic, cell) in enumerate(row):
                if len(cell) > 0:
                    self.interact(cell, ir, ic)

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
        if self.players[player].snippets >= 0:
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
        if (self.turn % CODE_SPAWN_DELAY == 0):
            self.spawn_snippet()
        if (self.turn % WEAPON_SPAWN_DELAY == 0):
            self.spawn_weapon()
        self.text_board()
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

