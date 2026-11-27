"""The first whiteboard object library: what explainers actually draw. One line per object: `id: what to draw` (the words given to the image model).

Chosen from the things explainer videos point at again and again: the nouns of school science, health, money, work and technology, the standard metaphors
(target, ladder, puzzle, scales, light bulb), simple people in a few poses, a few expressive faces, and symbols. Ids are stable; search is by meaning
(lib_index.py), so the id only has to be unique and readable. Titles, synonyms (EN/ES), tags and descriptions are written by the quality gate's model
when it looks at the finished drawing (lib_build.py).
"""
from typing import Dict, List, Tuple

PERSON = "a simple person with a round head and NO face, simple body with arms and legs, "
FACE = "a simple round face (just a circle head, two dot eyes, simple mouth, no nose, no hair), "

CATEGORIES: Dict[str, str] = {
    "nature": """
sun: a sun, a circle with short straight rays around it
cloud: a fluffy cumulus cloud
rain_cloud: a rain cloud with short rain strokes falling from it
storm_cloud: a storm cloud with one lightning bolt under it
mountain: a mountain with a zigzag snow cap on its peak
sea_waves: a patch of sea, three rows of rolling ocean waves
plant_sprout: a small plant growing from a little mound of soil, one stem with four leaves
tree: a leafy tree with a round crown and a trunk
pine_tree: a pine tree
flower: a flower with five petals, a stem and two leaves
leaf: a single leaf with a centre vein
snowflake: a six-armed snowflake
water_drop: a single water drop
river: a winding river between two banks
moon: a crescent moon
star: a five-pointed star
rainbow: a rainbow of three arcs with a small cloud at each end
volcano: a volcano with a little smoke puff above it
island: a small island with one palm tree
cactus: a cactus with two arms
mushroom: a mushroom
fire: a campfire flame
wind: three curled wind lines
lightning: a lightning bolt
earth_globe: planet Earth as a globe with simple continents
seed: a seed with a tiny root and a tiny shoot
roots: a plant stem with roots spreading under a ground line
forest: three simple trees side by side
desert_dune: two sand dunes with a small sun above
iceberg: an iceberg, a small part above a water line and a big part below
""",
    "animals": """
fish: a fish
bird: a small bird standing
butterfly: a butterfly with open wings
bee: a bee
dog: a sitting dog, simple cartoon
cat: a sitting cat, simple cartoon
cow: a cow standing, side view, simple
chicken: a hen
frog: a frog sitting
snail: a snail
ant: an ant, side view
whale: a whale with a small water spout
turtle: a turtle, side view
rabbit: a rabbit sitting
elephant: an elephant, side view, simple
owl: an owl
spider_web: a spider web
paw_print: a paw print
egg: an egg
dinosaur: a friendly long-necked dinosaur, side view
""",
    "science": """
atom: an atom, a nucleus with three elliptical electron orbits
molecule: a water molecule, one big circle joined to two smaller circles
dna: a DNA double helix
microscope: a microscope
telescope: a telescope on a tripod
flask: a conical laboratory flask with liquid and bubbles
test_tube: a test tube with liquid
magnet: a horseshoe magnet
battery: a battery with plus and minus ends
light_bulb: a light bulb with short rays
gear: a single gear wheel
two_gears: two gear wheels meshing
rocket: a rocket flying upward
planet: a planet with a ring
satellite: a satellite with two solar panels
magnifier: a magnifying glass
thermometer: a thermometer
prism: a triangular prism splitting a ray into three rays
pendulum: a pendulum hanging from a bar
spring: a coiled spring
lever: a lever, a plank balanced on a triangle
pulley: a pulley wheel with a rope and a weight
beaker: a beaker with measurement ticks and liquid
petri_dish: a petri dish with small dots
cell: a biological cell, an outer blob with a nucleus and a few small organelles
virus: a virus, a circle with small knobbed spikes all around
bacteria: a rod-shaped bacterium with small hairs
solar_panel: a solar panel on a stand
wind_turbine: a wind turbine with three blades
circuit: a simple electric circuit, a battery joined by wires to a small lamp
compass: a navigation compass
funnel: a funnel
scale_balance: a balance scale with two pans
brain: a human brain, side view
""",
    "health": """
heart: a heart shape
heart_organ: an anatomical human heart, simple
lungs: a pair of lungs
stomach: a human stomach
tooth: a tooth
eye: an eye
ear: an ear
hand: an open hand, palm facing
bone: a bone
syringe: a syringe
pill: a capsule pill and a round tablet
medicine_bottle: a medicine bottle with a cross on the label
stethoscope: a stethoscope
bandage: an adhesive bandage
first_aid: a first aid kit box with a cross
hospital: a hospital building with a cross
shield_check: a shield with a check mark
antibody: three Y-shaped antibodies
apple: an apple with a leaf
carrot: a carrot
dumbbell: a dumbbell
bed: a bed with a pillow, side view
soap_hands: two hands washing with bubbles
mask: a face mask with ear loops
wheelchair: a wheelchair, side view
heartbeat: a heartbeat line with one spike
glass_water: a glass of water
running_shoe: a running shoe
""",
    "people": f"""
person_standing: {PERSON}standing straight
person_waving: {PERSON}one arm raised in a wave
person_walking: {PERSON}walking, side view
person_running: {PERSON}running, side view
person_pointing: {PERSON}pointing to the right with one arm
person_thinking: {PERSON}one hand on the chin, thinking
person_sitting: {PERSON}sitting on a chair, side view
person_cheering: {PERSON}both arms raised in joy
person_sad: {PERSON}standing with head down and shoulders dropped
person_carrying: {PERSON}carrying a box
person_presenting: {PERSON}standing next to a flip chart, pointing at it
person_desk: {PERSON}sitting at a desk with a laptop
two_talking: two simple round-headed people with no faces facing each other, a speech bubble between them
handshake_people: two simple round-headed people with no faces shaking hands
group_three: three simple round-headed people with no faces standing side by side
family: two adults and one child, simple round-headed people with no faces, holding hands
child: a simple small child with a round head and no face, arms out
baby: a simple baby sitting, round head and no face
teacher: {PERSON}pointing at a blackboard with a stick
doctor: {PERSON}wearing a doctor's coat with a stethoscope
scientist: {PERSON}wearing a lab coat and holding a flask
farmer: {PERSON}wearing a hat and holding a pitchfork
worker: {PERSON}wearing a hard hat and holding a wrench
chef: {PERSON}wearing a chef hat and holding a spoon
customer: {PERSON}pushing a shopping cart
leader: {PERSON}holding a flag
old_person: {PERSON}slightly bent, walking with a cane
person_question: {PERSON}shrugging with a question mark above the head
person_idea: {PERSON}with a small light bulb above the head
person_climbing: {PERSON}climbing a staircase
""",
    "faces": f"""
face_happy: {FACE}a big smile
face_sad: {FACE}a downturned mouth and one tear
face_surprised: {FACE}raised eyebrows and an open round mouth
face_angry: {FACE}slanted eyebrows and a frown
face_thinking: {FACE}one raised eyebrow, a small flat mouth, looking up
face_worried: {FACE}raised inner eyebrows and a wavy mouth
face_laughing: {FACE}closed arc eyes and a wide open laughing mouth
face_neutral: {FACE}a straight line mouth
face_sleepy: {FACE}closed eyes and a small z above
face_love: {FACE}heart-shaped eyes and a smile
face_sick: {FACE}a wavy mouth and a thermometer in the mouth
face_wink: {FACE}one eye winking and a smile
""",
    "business": """
bar_chart: a bar chart with four rising bars on two axes
line_chart: a line chart with a rising zigzag line and an arrow on two axes
pie_chart: a pie chart with one slice pulled out
target: a target with an arrow in the bullseye
briefcase: a briefcase
handshake: two hands shaking
trophy: a trophy cup
medal: a medal on a ribbon
calendar: a wall calendar page with a grid
clipboard: a clipboard with a checklist
document: a sheet of paper with a folded corner and lines
folder: a file folder
envelope: an envelope
megaphone: a megaphone
flag: a flag on a pole
ladder: a ladder
stairs: a staircase of four steps going up
puzzle_piece: a single jigsaw puzzle piece
puzzle_two: two jigsaw puzzle pieces fitting together
chess_knight: a chess knight piece
factory: a factory with two chimneys and smoke
office_building: an office building with windows
shop: a small shop with an awning and a door
delivery_truck: a delivery truck, side view
box_package: a cardboard box
shopping_cart: a shopping cart
shopping_bag: a shopping bag
price_tag: a price tag with a string
contract: a contract page with a signature line and a pen
podium: a winners podium with three steps
org_chart: an organisation chart, one box on top joined to three boxes below
funnel_sales: a wide funnel with three small circles falling in and one coming out
rocket_launch: a rocket lifting off with a smoke cloud
crown: a crown
key: a key
lock: a padlock
tools: a crossed wrench and screwdriver
hourglass: an hourglass
""",
    "money": """
coin: a coin with a simple star in the centre
coin_stack: three stacks of coins of rising height
banknote: a banknote with a circle in the centre
piggy_bank: a piggy bank with a coin dropping in
wallet: a wallet
credit_card: a credit card
bank: a bank building with columns
money_bag: a money bag tied at the neck
safe: a safe with a dial
calculator: a calculator
receipt: a long receipt with lines
growth_plant: a small plant growing out of a stack of coins
percent: a large percent sign
scales_justice: scales of justice on a stand
cash_register: a cash register
gold_bars: three stacked gold bars
house_price: a house with a price tag hanging from it
diamond: a cut diamond
treasure_chest: an open treasure chest
tax_form: a form page with a large check box and a pencil
""",
    "technology": """
laptop: an open laptop
smartphone: a smartphone
desktop: a desktop monitor with a keyboard
tablet: a tablet with a stylus
server: a server rack with three units
cloud_upload: a cloud with an arrow pointing up into it
wifi: a wifi symbol, a dot with three arcs
robot: a friendly robot with a square head and antenna
chip: a computer chip with pins on four sides
database: a database cylinder of three stacked discs
network: five circles joined by lines in a network
camera: a photo camera
video_camera: a video camera on a tripod
headphones: headphones
microphone: a microphone on a stand
speaker: a loudspeaker with sound waves
printer: a printer with a sheet coming out
mouse: a computer mouse with a cable
keyboard: a computer keyboard
usb: a USB stick
email: an envelope with an at sign
chat_bubbles: two overlapping speech bubbles
code_window: a browser window with angle brackets inside
bug: a beetle bug, top view
satellite_dish: a satellite dish
drone: a drone with four rotors
car_electric: a car with a plug cable, side view
plug: an electric plug
switch: a light switch
television: a television
game_controller: a game controller
watch: a wristwatch
""",
    "places": """
house: a little house with a pitched roof, a door and a window
school: a school building with a flag and a clock
city: a skyline of four buildings of different heights
bridge: a suspension bridge
road: a winding road going to the horizon
lighthouse: a lighthouse
castle: a castle with two towers
church: a small church with a steeple
tent: a camping tent
barn: a barn with a big door
windmill: a traditional windmill
museum: a museum building with columns and steps
airport_tower: an airport control tower
map: a folded map with a location pin
location_pin: a location pin
signpost: a signpost with two arrows pointing opposite ways
park_bench: a park bench
fountain: a fountain
street_lamp: a street lamp
traffic_light: a traffic light
""",
    "transport": """
car: a car, side view
bus: a bus, side view
bicycle: a bicycle
train: a train locomotive, side view
airplane: an airplane, side view
ship: a cargo ship
sailboat: a sailboat
hot_air_balloon: a hot air balloon
helicopter: a helicopter
truck: a truck, side view
motorbike: a motorbike, side view
scooter: a kick scooter
tractor: a tractor
submarine: a submarine
ambulance: an ambulance, side view
anchor: an anchor
wheel: a wheel with spokes
fuel_pump: a fuel pump
parachute: a parachute with a box
paper_plane: a paper plane
""",
    "home_food": """
cup: a cup of hot coffee with steam
bottle: a bottle
bread: a loaf of bread
cheese: a wedge of cheese with holes
pizza: a slice of pizza
cake: a birthday cake with one candle
banana: a banana
milk: a milk carton
pot: a cooking pot with a lid and steam
fridge: a refrigerator
chair: a chair
table: a table
sofa: a sofa
lamp: a table lamp
door: a door, slightly open
window: a window with four panes and a curtain
clock: a round wall clock
alarm_clock: an alarm clock with two bells
book: an open book
books_stack: a stack of three books
pencil: a pencil
backpack: a school backpack
scissors: scissors
umbrella: an open umbrella
trash_bin: a trash bin
recycle_bin: a bin with three chasing arrows on it
bucket: a bucket of water
broom: a broom
toothbrush: a toothbrush
gift: a gift box with a ribbon
balloon: a party balloon on a string
candle: a burning candle
tap: a water tap with a drop
washing_machine: a washing machine
tshirt: a t-shirt
glasses: a pair of glasses
hat: a hat
fork_knife: a crossed fork and knife
""",
    "symbols": """
check_mark: a large check mark
cross_mark: a large X mark
question_mark: a large question mark
exclamation: a large exclamation mark
arrow_up: a thick outlined arrow pointing up
arrow_down: a thick outlined arrow pointing down
arrow_right: a thick outlined arrow pointing right
cycle_arrows: three curved arrows chasing each other in a circle
plus: a thick outlined plus sign
minus: a thick outlined minus sign
equals: a thick outlined equals sign
infinity: an infinity sign
speech_bubble: an empty speech bubble
thought_bubble: an empty thought bubble with small circles
warning: a warning triangle with an exclamation mark
stop_sign: an octagonal stop sign shape, empty
thumbs_up: a thumbs up hand
thumbs_down: a thumbs down hand
peace_dove: a dove with an olive branch
recycle: the recycling symbol of three arrows
globe_grid: a globe with latitude and longitude lines
magnet_attract: a horseshoe magnet pulling three small circles
explosion: a spiky explosion burst shape
spark: three small four-pointed sparkles
music_note: a music note
bell: a bell
eye_crossed: an eye with a diagonal line through it
no_sign: a circle with a diagonal bar, the prohibition sign
power: the power on symbol
link_chain: two chain links joined
""",
    "time_ideas": """
stopwatch: a stopwatch
sand_timer: a sand timer running
sunrise: a half sun rising over a horizon line with rays
calendar_day: a calendar page with one day circled
history_scroll: a paper scroll
road_fork: a road splitting into two paths with a signpost
mountain_flag: a mountain with a flag on the peak
maze: a simple square maze
domino: three dominoes falling
balance_seesaw: a seesaw with a big ball on one side and a small ball on the other
snowball: a snowball rolling down a slope and growing
tip_iceberg: a boat next to an iceberg tip
bridge_gap: a gap between two cliffs with a plank across
door_open: an open door with light rays coming out
ladder_wall: a ladder leaning on a wall
knot: a rope with a knot
seedling_hands: two hands holding a small plant
compass_rose: a compass rose with four points
telescope_star: a telescope pointing at a star
anchor_chain: an anchor with a short chain
""",
}

# Natural accents the gate's model may choose from when it colours the enclosed areas.
SKIP: List[str] = []


def objects() -> List[Tuple[str, str, str]]:
    """-> [(id, category, what to draw)] in a stable order."""
    out, seen = [], set()
    for cat, block in CATEGORIES.items():
        for line in block.strip().splitlines():
            oid, what = line.split(":", 1)
            oid = oid.strip()
            assert oid not in seen, oid
            seen.add(oid)
            out.append((oid, cat, what.strip()))
    return out


if __name__ == "__main__":
    o = objects()
    from collections import Counter

    print(len(o), "objects;", dict(Counter(c for _, c, _ in o)))
