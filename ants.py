"""The ants module implements game logic for Ants Vs. SomeBees."""

import random
import sys
from ucb import main, interact, trace
from collections import OrderedDict


################
# Core Classes #
################


class Place:
    """A Place holds insects and has an exit to another Place."""

    def __init__(self, name, exit=None):
        """Create a Place with the given exit.

        name -- A string; the name of this Place.
        exit -- The Place reached by exiting this Place (may be None).
        """
        self.name, self.exit, self.bees, self.ant, self.entrance = name, exit, [], None, None
        if exit:
            exit.entrance = self

    def add_insect(self, insect):
        """Add an Insect to this Place.

        There can be at most one Ant in a Place, unless exactly one of them is
        a BodyguardAnt (Phase 4), in which case there can be two. If add_insect
        tries to add more Ants than is allowed, an assertion error is raised.

        There can be any number of Bees in a Place.
        """
        if insect.is_ant:
            if self.ant:
                assert self.ant.can_contain(insect) or insect.can_contain(self.ant), 'Two ants in {0}'.format(self)
                if self.ant.can_contain(insect):
                    self.ant.contain_ant(insect)
                elif insect.can_contain(self.ant):
                    insect.contain_ant(self.ant)
                    self.ant = insect
            else:
                self.ant = insect
        else:
            self.bees.append(insect)
        insect.place = self

    def remove_insect(self, insect):
        """Remove an Insect from this Place."""
        if insect.is_ant:
            assert self.ant == insect, '{0} is not in {1}'.format(insect, self)
            if insect.container and insect.ant:
                self.ant = None
                self.add_insect(insect.ant)
            elif type(insect)==QueenAnt and insect.original:
                self.ant = self.ant
            else:
                self.ant = None
        else:
            self.bees.remove(insect)
        insect.place = None

    def __str__(self):
        return self.name


class Insect:
    """An Insect, the base class of Ant and Bee, has armor and a Place."""

    is_ant, watersafe = False, False

    def __init__(self, armor, place=None):
        """Create an Insect with an armor amount and a starting Place."""
        self.armor, self.place = armor, place

    def reduce_armor(self, amount):
        """Reduce armor by amount, and remove the insect from its place if it
        has no armor remaining.

        >>> test_insect = Insect(5)
        >>> test_insect.reduce_armor(2)
        >>> test_insect.armor
        3
        """
        self.armor -= amount
        if self.armor <= 0:
            print('{0} ran out of armor and expired'.format(self))
            self.place.remove_insect(self)

    def action(self, colony):
        """The action performed each turn.

        colony -- The AntColony, used to access game state information.
        """

    def __repr__(self):
        cname = type(self).__name__
        return '{0}({1}, {2})'.format(cname, self.armor, self.place)


class Bee(Insect):
    """A Bee moves from place to place, following exits and stinging ants."""

    name, watersafe = 'Bee', True

    def sting(self, ant):
        """Attack an Ant, reducing the Ant's armor by 1."""
        ant.reduce_armor(1)

    def move_to(self, place):
        """Move from the Bee's current Place to a new Place."""
        self.place.remove_insect(self)
        place.add_insect(self)

    def blocked(self):
        """Return True if this Bee cannot advance to the next Place."""
        return self.place.ant and self.place.ant.blocks_path

    def action(self, colony):
        """A Bee's action stings the Ant that blocks its exit if it is blocked,
        or moves to the exit of its current place otherwise.

        colony -- The AntColony, used to access game state information.
        """
        if self.blocked():
            self.sting(self.place.ant)
        elif self.place is not colony.hive and self.armor > 0:
            self.move_to(self.place.exit)


class Ant(Insect):
    """An Ant occupies a place and does work for the colony."""

    is_ant, implemented, damage, food_cost, blocks_path, container = True, True, 0, 0, True, False

    def __init__(self, armor=1):
        """Create an Ant with an armor quantity."""
        Insect.__init__(self, armor)

    def can_contain(self, other):
        return self.container and not self.ant and not other.container

class HarvesterAnt(Ant):
    """HarvesterAnt produces 1 additional food per turn for the colony."""

    name, implemented, food_cost = 'Harvester', True, 2

    def action(self, colony):
        """Produce 1 additional food for the colony.

        colony -- The AntColony, used to access game state information.
        """
        colony.food += 1


def random_or_none(s):
    """Return a random element of sequence s, or return None if s is empty."""
    if s:
        return random.choice(s)


class ThrowerAnt(Ant):
    """ThrowerAnt throws a leaf each turn at the nearest Bee in its range."""

    name, implemented, damage, food_cost, min_range, max_range = 'Thrower', True, 1, 4, 0, 10

    def nearest_bee(self, hive):
        """Return the nearest Bee in a Place that is not the Hive, connected to
        the ThrowerAnt's Place by following entrances.

        This method returns None if there is no such Bee (or none in range).
        """
        current_place, current_range = self.place, 0
        while current_place:
            random_bee = random_or_none(current_place.bees)
            if current_place != hive and random_bee and current_range >= self.min_range and current_range <= self.max_range:
                return random_bee
            current_place, current_range = current_place.entrance, current_range + 1
        return None

    def throw_at(self, target):
        """Throw a leaf at the target Bee, reducing its armor."""
        if target is not None:
            target.reduce_armor(self.damage)

    def action(self, colony):
        """Throw a leaf at the nearest Bee in range."""
        self.throw_at(self.nearest_bee(colony.hive))


class Hive(Place):
    """The Place from which the Bees launch their assault.

    assault_plan -- An AssaultPlan; when & where bees enter the colony.
    """

    def __init__(self, assault_plan):
        self.name = 'Hive'
        self.assault_plan = assault_plan
        self.bees = []
        for bee in assault_plan.all_bees:
            self.add_insect(bee)
        # The following attributes are always None for a Hive
        self.entrance = None
        self.ant = None
        self.exit = None

    def strategy(self, colony):
        exits = [p for p in colony.places.values() if p.entrance is self]
        for bee in self.assault_plan.get(colony.time, []):
            bee.move_to(random.choice(exits))


class AntColony:
    """An ant collective that manages global game state and simulates time.

    Attributes:
    time -- elapsed time
    food -- the colony's available food total
    queen -- the place where the queen resides
    places -- A list of all places in the colony (including a Hive)
    bee_entrances -- A list of places that bees can enter
    """

    def __init__(self, strategy, hive, ant_types, create_places, food=2):
        """Create an AntColony for simulating a game.

        Arguments:
        strategy -- a function to deploy ants to places
        hive -- a Hive full of bees
        ant_types -- a list of ant constructors
        create_places -- a function that creates the set of places
        """
        self.time = 0
        self.food = food
        self.strategy = strategy
        self.hive = hive
        self.ant_types = OrderedDict((a.name, a) for a in ant_types)
        self.configure(hive, create_places)

    def configure(self, hive, create_places):
        """Configure the places in the colony."""
        self.queen = Place('AntQueen')
        self.places = OrderedDict()
        self.bee_entrances = []
        def register_place(place, is_bee_entrance):
            self.places[place.name] = place
            if is_bee_entrance:
                place.entrance = hive
                self.bee_entrances.append(place)
        register_place(self.hive, False)
        create_places(self.queen, register_place)

    def simulate(self):
        """Simulate an attack on the ant colony (i.e., play the game)."""
        while len(self.queen.bees) == 0 and len(self.bees) > 0:
            self.hive.strategy(self)    # Bees invade
            self.strategy(self)         # Ants deploy
            for ant in self.ants:       # Ants take actions
                if ant.armor > 0:
                    ant.action(self)
            for bee in self.bees:       # Bees take actions
                if bee.armor > 0:
                    bee.action(self)
            self.time += 1
        if len(self.queen.bees) > 0:
            print('The ant queen has perished. Please try again.')
        else:
            print('All bees are vanquished. You win!')

    def deploy_ant(self, place_name, ant_type_name):
        """Place an ant if enough food is available.

        This method is called by the current strategy to deploy ants.
        """
        constructor = self.ant_types[ant_type_name]
        if self.food < constructor.food_cost:
            print('Not enough food remains to place ' + ant_type_name)
        else:
            self.places[place_name].add_insect(constructor())
            self.food -= constructor.food_cost

    def remove_ant(self, place_name):
        """Remove an Ant from the Colony."""
        place = self.places[place_name]
        if place.ant is not None:
            place.remove_insect(place.ant)

    @property
    def ants(self):
        return [p.ant for p in self.places.values() if p.ant is not None]

    @property
    def bees(self):
        return [b for p in self.places.values() for b in p.bees]

    @property
    def insects(self):
        return self.ants + self.bees

    def __str__(self):
        status = ' (Food: {0}, Time: {1})'.format(self.food, self.time)
        return str([str(i) for i in self.ants + self.bees]) + status


def ant_types():
    """Return a list of all implemented Ant classes."""
    all_ant_types = []
    new_types = [Ant]
    while new_types:
        new_types = [t for c in new_types for t in c.__subclasses__()]
        all_ant_types.extend(new_types)
    return [t for t in all_ant_types if t.implemented]

def interactive_strategy(colony):
    """A strategy that starts an interactive session and lets the user make
    changes to the colony.

    For example, one might deploy a ThrowerAnt to the first tunnel by invoking
    colony.deploy_ant('tunnel_0_0', 'Thrower')
    """
    print('colony: ' + str(colony))
    msg = '<Control>-D (<Control>-Z <Enter> on Windows) completes a turn.\n'
    interact(msg)

def start_with_strategy(args, strategy):
    """Reads command-line arguments and starts a game with those options."""
    import argparse
    parser = argparse.ArgumentParser(description="Play Ants vs. SomeBees")
    parser.add_argument('-f', '--full', action='store_true',
                        help='loads a full layout and assault plan')
    parser.add_argument('-w', '--water', action='store_true',
                        help='loads a full layout with water')
    parser.add_argument('-i', '--insane', action='store_true',
                        help='loads a difficult assault plan')
    parser.add_argument('--food', type=int,
                        help='number of food to start with', default=2)
    args = parser.parse_args()

    assault_plan = make_test_assault_plan()
    layout = test_layout
    food = args.food
    if args.full:
        assault_plan = make_full_assault_plan()
        layout = dry_layout
    if args.water:
        layout = wet_layout
    if args.insane:
        assault_plan = make_insane_assault_plan()
    hive = Hive(assault_plan)
    AntColony(strategy, hive, ant_types(), layout, food).simulate()


###########
# Layouts #
###########

def wet_layout(queen, register_place, length=8, tunnels=3, moat_frequency=3):
    """Register a mix of wet and and dry places."""
    for tunnel in range(tunnels):
        exit = queen
        for step in range(length):
            if moat_frequency != 0 and (step + 1) % moat_frequency == 0:
                exit = Water('water_{0}_{1}'.format(tunnel, step), exit)
            else:
                exit = Place('tunnel_{0}_{1}'.format(tunnel, step), exit)
            register_place(exit, step == length - 1)

def dry_layout(queen, register_place, length=8, tunnels=3):
    """Register dry tunnels."""
    wet_layout(queen, register_place, length, tunnels, 0)

def test_layout(queen, register_place, length=8):
    """Register a single dry tunnel."""
    dry_layout(queen, register_place, length, 1)


#################
# Assault Plans #
#################


class AssaultPlan(dict):
    """The Bees' plan of attack for the Colony.  Attacks come in timed waves.

    An AssaultPlan is a dictionary from times (int) to waves (list of Bees).

    >>> AssaultPlan().add_wave(4, 2)
    {4: [Bee(3, None), Bee(3, None)]}
    """

    def __init__(self, bee_armor=3):
        self.bee_armor = bee_armor

    def add_wave(self, time, count):
        """Add a wave at time with count Bees that have the specified armor."""
        bees = [Bee(self.bee_armor) for _ in range(count)]
        self.setdefault(time, []).extend(bees)
        return self

    @property
    def all_bees(self):
        """Place all Bees in the hive and return the list of Bees."""
        return [bee for wave in self.values() for bee in wave]

def make_test_assault_plan():
    return AssaultPlan().add_wave(2, 1).add_wave(3, 1)

def make_full_assault_plan():
    plan = AssaultPlan().add_wave(2, 1)
    for time in range(3, 15, 2):
        plan.add_wave(time, 1)
    return plan.add_wave(15, 8)

def make_insane_assault_plan():
    plan = AssaultPlan(4).add_wave(1, 2)
    for time in range(3, 15):
        plan.add_wave(time, 1)
    return plan.add_wave(15, 20)

##############
# Extensions #
##############

class Water(Place):
    """Water is a place that can only hold 'watersafe' insects."""

    def add_insect(self, insect):
        """Add insect if it is watersafe, otherwise reduce its armor to 0."""
        print('added', insect, insect.watersafe)
        Place.add_insect(self, insect)
        if not insect.watersafe:
            insect.reduce_armor(insect.armor)


class FireAnt(Ant):
    """FireAnt cooks any Bee in its Place when it expires."""

    name, damage, food_cost, implemented = 'Fire', 3, 4, True

    def reduce_armor(self, amount):
        self.armor -= amount
        if self.armor <= 0:
            bee_list = self.place.bees[:]
            for bee in bee_list:
                bee.reduce_armor(self.damage)


class LongThrower(ThrowerAnt):
    """A ThrowerAnt that only throws leaves at Bees at least 4 places away."""

    name, food_cost, implemented, min_range, max_range = 'Long', 3, True, 4, float("inf")
        

class ShortThrower(ThrowerAnt):
    """A ThrowerAnt that only throws leaves at Bees less than 3 places away."""

    name, food_cost, implemented, min_range, max_range = 'Short', 3, True, 0, 2


class WallAnt(Ant):
    food_cost, name, implemented = 4, 'Wall', True

    def __init__(self, armor=4):
        """Create an Ant with an armor quantity."""
        Ant.__init__(self, armor)


class NinjaAnt(Ant):
    """NinjaAnt does not block the path and damages all bees in its place."""

    name, damage, food_cost, blocks_path, implemented = 'Ninja', 1, 6, False, True

    def action(self, colony):
        ninja_bees = self.place.bees[:]
        for bee in ninja_bees:
            bee.reduce_armor(self.damage)


class ScubaThrower(ThrowerAnt):
    food_cost, watersafe = 5, True


class HungryAnt(Ant):
    """HungryAnt will take three turns to digest a Bee in its place.
    While digesting, the HungryAnt can't eat another Bee.
    """

    name, time_to_digest, food_cost, implemented = 'Hungry', 3, 4, True

    def __init__(self):
        Ant.__init__(self)
        self.digesting = 0

    def eat_bee(self, bee):
        bee.reduce_armor(bee.armor)

    def action(self, colony):
        if self.digesting:
            self.digesting -= 1
        elif len(self.place.bees) > 0:
            self.eat_bee(random_or_none(self.place.bees))
            self.digesting = self.time_to_digest


class BodyguardAnt(Ant):
    """BodyguardAnt provides protection to other Ants."""

    name, container, implemented, food_cost = 'Bodyguard', True, True, 4

    def __init__(self):
        Ant.__init__(self, 2)
        self.ant = None  # The Ant hidden in this bodyguard

    def contain_ant(self, ant):
        self.ant = ant

    def action(self, colony):
        if self.ant:
            self.ant.action(colony)


class QueenPlace:
    """A place that represents both places in which the bees find the queen.

    (1) The original colony queen location at the end of all tunnels, and
    (2) The place in which the QueenAnt resides.
    """
    def __init__(self, colony_queen, ant_queen):
        self.colony_queen, self.ant_queen = colony_queen, ant_queen

    @property
    def bees(self):
        return self.colony_queen.bees + self.ant_queen.bees


class QueenAnt(ScubaThrower):
    """The Queen of the colony.  The game is over if a bee enters her place."""

    name, food_cost, count_queens, implemented, ant_list = 'Queen', 6, 0, True, []

    def __init__(self):
        ScubaThrower.__init__(self)
        QueenAnt.count_queens += 1
        if QueenAnt.count_queens > 1:
            self.original = False
        else:
            self.original = True

    def action(self, colony):
        """A queen ant throws a leaf, but also doubles the damage of ants
        in her tunnel.

        Impostor queens do only one thing: reduce their own armor to 0.
        """
        if self.original:
            def double_and_add(ant): # Doubles the damage of ant and adds the ant to self.ant_list
                ant.damage *= 2
                self.ant_list += [ant]
            if self.place.ant.container and self.place.ant not in self.ant_list:
                double_and_add(self.place.ant)
            def traverse(direction):
                current_place = getattr (self.place, direction)
                while current_place:
                    if current_place.ant and current_place.ant not in self.ant_list:
                        double_and_add(current_place.ant)
                        if current_place.ant.container and current_place.ant.ant:
                            double_and_add(current_place.ant.ant)
                    current_place = getattr (current_place, direction)
            traverse('exit')
            traverse('entrance')
            colony.queen = QueenPlace (self.place, colony.queen)
            ThrowerAnt.action(self, colony) 
        else:
            self.reduce_armor(self.armor)

class AntRemover(Ant):
    """Allows the player to remove ants from the board in the GUI."""

    name = 'Remover'
    implemented = True

    def __init__(self):
        Ant.__init__(self, 0)


##################
# Status Effects #
##################

def make_slow(action):
    """Return a new action method that calls action every other turn.

    action -- An action method of some Bee
    """
    def action_make_slow(colony):
        if colony.time % 2 == 0:
            return action(colony)
    return action_make_slow

def make_stun(action):
    """Return a new action method that does nothing.

    action -- An action method of some Bee
    """
    def action_make_stun(colony):
        return
    return action_make_stun

def apply_effect(effect, bee, duration):
    """Apply a status effect to a Bee that lasts for duration turns."""
    old_action = bee.action
    def new_action(colony):
        nonlocal duration
        if duration >= 1:
            duration -= 1
            effect(old_action)(colony)
        else:
            old_action(colony)
    bee.action = new_action


class SlowThrower(ThrowerAnt):
    """ThrowerAnt that causes Slow on Bees."""

    name, food_cost, implemented = 'Slow', 4, True

    def throw_at(self, target):
        if target:
            apply_effect(make_slow, target, 3)


class StunThrower(ThrowerAnt):
    """ThrowerAnt that causes Stun on Bees."""

    name, food_cost, implemented = 'Stun', 6, True

    def throw_at(self, target):
        if target:
            apply_effect(make_stun, target, 1)

@main
def run(*args):
    start_with_strategy(args, interactive_strategy)