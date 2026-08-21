"""A mock `bpy` sufficient to execute this addon's operators outside Blender.

Not a Blender emulator. It models just enough of the data API for the export and
transfer operators to run start to finish, so that NameError, AttributeError,
wrong-branch and ordering bugs surface in a normal Python process.

Blender ops are recorded rather than performed, except where the addon depends
on their side effects (nla.bake produces an action; mode_set updates the mode).
"""

import contextlib
import math


# ---------------------------------------------------------------- mathutils

class Matrix:
    """4x4 row-major matrix, only the operations the addon actually uses."""

    def __init__(self, rows=None):
        if rows is None:
            rows = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
        self.rows = [list(row) for row in rows]

    @staticmethod
    def from_loc_rot_z(location, z_radians=0.0):
        cos_z, sin_z = math.cos(z_radians), math.sin(z_radians)
        return Matrix([
            [cos_z, -sin_z, 0.0, location[0]],
            [sin_z,  cos_z, 0.0, location[1]],
            [0.0,      0.0, 1.0, location[2]],
            [0.0,      0.0, 0.0, 1.0],
        ])

    @staticmethod
    def Identity(size=4):
        return Matrix()

    def copy(self):
        return Matrix(self.rows)

    def __matmul__(self, other):
        result = [[sum(self.rows[r][k] * other.rows[k][c] for k in range(4))
                   for c in range(4)] for r in range(4)]
        return Matrix(result)

    def inverted_safe(self):
        try:
            return self.inverted()
        except ValueError:
            return Matrix()

    def inverted(self):
        """Gauss-Jordan on the 4x4."""
        a = [row[:] + [1.0 if i == j else 0.0 for j in range(4)]
             for i, row in enumerate(self.rows)]
        for col in range(4):
            pivot = max(range(col, 4), key=lambda r: abs(a[r][col]))
            if abs(a[pivot][col]) < 1e-12:
                raise ValueError("matrix not invertible")
            a[col], a[pivot] = a[pivot], a[col]
            scale = a[col][col]
            a[col] = [v / scale for v in a[col]]
            for r in range(4):
                if r == col:
                    continue
                factor = a[r][col]
                a[r] = [v - factor * w for v, w in zip(a[r], a[col])]
        return Matrix([row[4:] for row in a])

    @property
    def translation(self):
        return (self.rows[0][3], self.rows[1][3], self.rows[2][3])

    def __iter__(self):
        return iter(self.rows)

    def __eq__(self, other):
        if not isinstance(other, Matrix):
            return NotImplemented
        return all(
            abs(a - b) < 1e-6
            for row_a, row_b in zip(self.rows, other.rows)
            for a, b in zip(row_a, row_b)
        )

    def __repr__(self):
        return f"Matrix(loc={tuple(round(v, 4) for v in self.translation)})"


# ---------------------------------------------------------------- datablocks

class Bone:
    def __init__(self, name):
        self.name = name
        self.select = False


class PoseBone:
    def __init__(self, name):
        self.name = name
        self.bone = Bone(name)
        self.constraints = []


class Pose:
    def __init__(self, bone_names):
        self._bones = [PoseBone(n) for n in bone_names]

    def __iter__(self):
        return iter(self._bones)

    @property
    def bones(self):
        return _NamedList(self._bones)


class _NamedList:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        return self.get(key)

    def __contains__(self, key):
        return self.get(key) is not None

    def get(self, name, default=None):
        for item in self._items:
            if item.name == name:
                return item
        return default


class ArmatureData:
    def __init__(self, name, bone_names):
        self.name = name
        self.bones = _NamedList([Bone(n) for n in bone_names])

    def copy(self):
        return ArmatureData(self.name + ".copy", [b.name for b in self.bones])


class FCurve:
    def __init__(self, data_path):
        self.data_path = data_path
        self.keyframe_points = [_Key(), _Key()]

    def __repr__(self):
        return f"FCurve({self.data_path!r})"


class _Key:
    def __init__(self):
        self.interpolation = 'BEZIER'


class FCurves(list):
    def remove(self, fcurve):
        list.remove(self, fcurve)


class Slot:
    def __init__(self, name="Slot"):
        self.name = name


class PoseMarkers(list):
    def new(self, name):
        marker = type("Marker", (), {"name": name, "frame": 0})()
        self.append(marker)
        return marker

    def remove(self, marker):
        list.remove(self, marker)


class Action:
    def __init__(self, name, data_paths=(), frame_range=(1, 30)):
        self._name = name
        self.fcurves = FCurves(FCurve(p) for p in data_paths)
        self.layers = []                      # 4.4 shape not exercised here
        self.slots = [Slot()]
        self.pose_markers = PoseMarkers()
        self.curve_frame_range = frame_range
        self.frame_range = frame_range
        data.actions._register(self)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        # Blender appends .001 when the name is taken
        existing = data.actions.get(value)
        if existing is not None and existing is not self:
            suffix = 1
            while data.actions.get(f"{value}.{suffix:03d}"):
                suffix += 1
            value = f"{value}.{suffix:03d}"
        self._name = value

    def copy(self):
        clone = Action(self._name, [fc.data_path for fc in self.fcurves], self.curve_frame_range)
        return clone

    def __repr__(self):
        return f"Action({self._name!r})"


class AnimationData:
    def __init__(self):
        self.action = None
        self.action_slot = None


class Object:
    def __init__(self, name, obj_type='ARMATURE', bone_names=(), matrix=None):
        self._name = name
        self.type = obj_type
        self.data = ArmatureData(name + "Data", bone_names) if obj_type == 'ARMATURE' else None
        self.pose = Pose(bone_names) if obj_type == 'ARMATURE' else None
        self.animation_data = None
        self.constraints = _Constraints()
        self.children = []
        self.users = 1
        self.mode = 'OBJECT'
        self._custom = {}
        self._basis = matrix.copy() if matrix else Matrix()
        self._selected = False
        data.objects._register(self)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        existing = data.objects.get(value)
        if existing is not None and existing is not self:
            suffix = 1
            while data.objects.get(f"{value}.{suffix:03d}"):
                suffix += 1
            value = f"{value}.{suffix:03d}"
        self._name = value

    @property
    def matrix_basis(self):
        return self._basis

    @matrix_basis.setter
    def matrix_basis(self, value):
        self._basis = value.copy()

    @property
    def matrix_world(self):
        """Evaluate object-level constraints, as the depsgraph does.

        Child Of: world = target_world @ inverse_matrix @ basis. This is why
        assigning matrix_world on a constrained object does not stick.
        """
        result = self._basis
        for constraint in self.constraints:
            if constraint.type == 'CHILD_OF' and constraint.target is not None:
                result = constraint.target.matrix_world @ constraint.inverse_matrix @ result
        return result

    @matrix_world.setter
    def matrix_world(self, value):
        # Blender does NOT invert constraints out when you assign matrix_world;
        # it writes the basis. The constraint then re-applies on evaluation.
        self._basis = value.copy()

    @property
    def matrix_local(self):
        return self.matrix_world

    def animation_data_create(self):
        if self.animation_data is None:
            self.animation_data = AnimationData()
        return self.animation_data

    def select_set(self, state):
        self._selected = state

    def copy(self):
        clone = Object(self._name, self.type, [b.name for b in (self.data.bones if self.data else [])],
                       self._basis)
        if self.animation_data:
            clone.animation_data_create()
            clone.animation_data.action = self.animation_data.action
        return clone

    def __contains__(self, key):
        return key in self._custom

    def __getitem__(self, key):
        return self._custom[key]

    def __setitem__(self, key, value):
        self._custom[key] = value

    def __delitem__(self, key):
        del self._custom[key]

    def __repr__(self):
        return f"Object({self._name!r})"


class Constraint:
    def __init__(self, kind, target=None, inverse_matrix=None):
        self.type = kind
        self.name = kind
        self.target = target
        self.subtarget = ""
        self.owner_space = 'WORLD'
        self.target_space = 'WORLD'
        self.mute = False
        self.inverse_matrix = inverse_matrix.copy() if inverse_matrix else Matrix()


class _Constraints(list):
    def new(self, kind):
        constraint = Constraint(kind)
        self.append(constraint)
        return constraint


# ---------------------------------------------------------------- collections

class _DataCollection:
    def __init__(self):
        self._items = []

    def _register(self, item):
        self._items.append(item)

    def get(self, name, default=None):
        for item in self._items:
            if item.name == name:
                return item
        return default

    def remove(self, item, do_unlink=False):
        if item not in self._items:
            raise ReferenceError("already removed")
        self._items.remove(item)
        # Real Blender unlinks the datablock from every collection on remove.
        try:
            context.scene.collection.objects.unlink(item)
        except (AttributeError, ValueError):
            pass

    def values(self):
        return list(self._items)

    def __iter__(self):
        return iter(list(self._items))

    def __contains__(self, name):
        return self.get(name) is not None

    def __len__(self):
        return len(self._items)


class _Libraries:
    """Stands in for the reference .blend, with the real authored transforms."""

    CONTENTS = {}

    _pending = []

    @contextlib.contextmanager
    def load(self, filepath, link=False):
        self._pending = []
        source = _LibrarySide(list(self.CONTENTS))
        target = _LibrarySide([])
        yield source, target
        loaded = []
        for name in target.objects:
            spec = self.CONTENTS.get(name)
            if spec is None:
                loaded.append(None)
                continue
            obj = Object(name, 'ARMATURE', spec['bones'], spec['matrix'])
            # Appending an object drags its animation data in too.
            action_name = spec.get('action')
            if action_name:
                existing = data.actions.get(action_name)
                if existing is None:
                    existing = Action(action_name,
                                      [f'pose.bones["{b}"].location' for b in spec['bones']])
                obj.animation_data_create()
                obj.animation_data.action = existing
            child_of = spec.get('child_of')
            if child_of:
                child_target = data.objects.get(child_of['target'])
                constraint = Constraint('CHILD_OF', child_target, child_of.get('inverse'))
                obj.constraints.append(constraint)
                self._pending.append((obj, child_of['target']))
            loaded.append(obj)
        # resolve Child Of targets that were appended in the same batch
        for obj, target_name in self._pending:
            for constraint in obj.constraints:
                if constraint.type == 'CHILD_OF' and constraint.target is None:
                    constraint.target = data.objects.get(target_name)
        target.objects = loaded


class _LibrarySide:
    def __init__(self, objects):
        self.objects = objects


class _Data:
    def __init__(self):
        self.objects = _DataCollection()
        self.actions = _DataCollection()
        self.libraries = _Libraries()


data = _Data()


# ---------------------------------------------------------------- context

class _Collection:
    def __init__(self):
        self.objects = _SceneObjects()


class _SceneObjects:
    def __init__(self):
        self._items = []

    def link(self, obj):
        if obj not in self._items:
            self._items.append(obj)

    def unlink(self, obj):
        if obj in self._items:
            self._items.remove(obj)

    def get(self, name, default=None):
        for item in self._items:
            if item.name == name:
                return item
        return default

    def __contains__(self, key):
        return any(o.name == key for o in self._items) if isinstance(key, str) else key in self._items

    def __iter__(self):
        return iter(self._items)


class _Scene:
    def __init__(self):
        self.frame_start = 1
        self.frame_end = 30
        self.collection = _Collection()
        self._custom = {}

    def get(self, key, default=None):
        return self._custom.get(key, default)

    def __setitem__(self, key, value):
        self._custom[key] = value

    def __getitem__(self, key):
        return self._custom[key]


class _ViewLayer:
    def __init__(self):
        self.objects = type("VLObjects", (), {"active": None})()

    def update(self):
        pass


class _Area:
    def __init__(self):
        self.type = 'VIEW_3D'


class _AddonEntry:
    def __init__(self, preferences):
        self.preferences = preferences


class _Addons(dict):
    pass


class _Preferences:
    def __init__(self):
        self.addons = _Addons()


class _WindowManager:
    def __init__(self):
        self.keyconfigs = None

    def invoke_props_dialog(self, operator, title=""):
        return {'RUNNING_MODAL'}


class _Context:
    def __init__(self):
        self.object = None
        self.scene = _Scene()
        self.area = _Area()
        self.view_layer = _ViewLayer()
        self.preferences = _Preferences()
        self.window_manager = _WindowManager()
        self.mode = 'OBJECT'
        self.selected_objects = []
        self.selected_pose_bones = []


context = _Context()


# ---------------------------------------------------------------- ops

CALLS = []


class _OpNamespace:
    def __init__(self, prefix):
        self._prefix = prefix

    def __getattr__(self, name):
        full = f"{self._prefix}.{name}"

        def call(*args, **kwargs):
            CALLS.append((full, kwargs))
            return _OPS_EFFECTS.get(full, lambda **k: {'FINISHED'})(**kwargs)

        return call


def _effect_bake(**kwargs):
    """nla.bake replaces the active object's action with a baked one."""
    obj = context.view_layer.objects.active
    if obj is None or obj.animation_data is None:
        return {'FINISHED'}
    current = obj.animation_data.action
    if current is None:
        return {'FINISHED'}
    baked = Action("Baked Result", [fc.data_path for fc in current.fcurves], current.curve_frame_range)
    obj.animation_data.action = baked
    return {'FINISHED'}


def _effect_mode_set(mode='OBJECT', **kwargs):
    context.mode = mode
    if context.object:
        context.object.mode = mode
    return {'FINISHED'}


_OPS_EFFECTS = {
    'nla.bake': _effect_bake,
    'object.mode_set': _effect_mode_set,
}


class _Ops:
    def __getattr__(self, name):
        return _OpNamespace(name)


ops = _Ops()


# ---------------------------------------------------------------- types/props

class _PropStub:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class props:
    StringProperty = staticmethod(lambda **kw: _PropStub(**kw))
    BoolProperty = staticmethod(lambda **kw: _PropStub(**kw))
    IntProperty = staticmethod(lambda **kw: _PropStub(**kw))
    FloatProperty = staticmethod(lambda **kw: _PropStub(**kw))
    EnumProperty = staticmethod(lambda **kw: _PropStub(**kw))


class _OperatorBase:
    def report(self, level, message):
        REPORTS.append((tuple(level)[0], message))


REPORTS = []


class types:
    Operator = _OperatorBase
    Panel = type("Panel", (), {})
    AddonPreferences = type("AddonPreferences", (), {})
    PoseBone = PoseBone


_registered = []


class utils:
    @staticmethod
    def register_class(cls):
        _registered.append(cls)

    @staticmethod
    def unregister_class(cls):
        if cls in _registered:
            _registered.remove(cls)


class path:
    @staticmethod
    def abspath(value):
        return value.replace("//", "/tmp/blend/")


app = type("App", (), {"version": (4, 4, 0)})()


# ---------------------------------------------------------------- reset

def reset():
    global data, context, CALLS, REPORTS
    data.objects = _DataCollection()
    data.actions = _DataCollection()
    context.__init__()
    CALLS.clear()
    REPORTS.clear()
