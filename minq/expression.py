__author__ = 'stevet'
import itertools
import re

import maya.cmds as cmds


def extension(self, name):
    target_class = ExpressionMeta.get_type(name)
    if target_class is False:
        raise NameError, "No Expression named " + name
    return self.compose(target_class)


class ExpressionMeta(type):
    _CLASSES = {}

    def __new__(cls, name, bases, dct):
        dct['__getattr__'] = extension
        ExpressionMeta._CLASSES[name] = type.__new__(cls, name, bases, dct)
        return ExpressionMeta._CLASSES[name]

    @staticmethod
    def get_type(name):
        return ExpressionMeta._CLASSES.get(name, False)


class Expression(object):
    __metaclass__ = ExpressionMeta

    def __init__(self, *args, **flags):
        self.command = flags.get('command', lambda p: p)
        if 'command' in flags:
            del flags['command']
        self.flags = flags
        self.args = args

    def _eval(self):
        result = self.command(*self.args, **self.flags)
        return result

    def eval(self):
        return tuple(self._eval() or tuple())

    def _format_expression(self, command, args, flags):
        cmd = command.__module__ + "." + command.__name__
        arglist = []
        if len(args):
            arglist.append("\n\t*" + args.__repr__())
        if len(flags):
            arglist.append("\n\t**" + flags.__repr__())
        return "{}({})".format(cmd, ",".join(arglist))

    def __iter__(self):
        return iter(self._eval() or tuple())

    def __repr__(self):
        return self._format_expression(self.command, self.args, self.flags)

    def __call__(self, *args, **flags):
        self.args = args
        self.flags = flags

    def compose(self, other):
        return DisjointExpression(self, other())


class ChainedExpression(Expression):
    def __init__(self, expr1, expr2):
        self.upstream = expr1
        self.downstream = expr2

    def _concat(self):
        args = self.upstream.args + self.downstream.args
        flags = dict(self.upstream.flags)
        flags.update(self.downstream.flags)
        return args, flags

    def _eval(self):
        args, flags = self._concat()
        return self.downstream.command(*args, **flags)


    def __repr__(self):
        args, flags = self._concat()
        cmd = self.upstream.command
        return self._format_expression(cmd, args, flags)

    def __call__(self, *args, **kwargs):
        self.downstream(*args, **kwargs)
        return self


class DisjointExpression(Expression):
    def __init__(self, expr1, expr2):
        self.upstream = expr1
        self.downstream = expr2

    def _eval(self):
        return self.downstream.command(*self.upstream.eval(), **self.downstream.flags)

    def __repr__(self):
        flags = self.downstream.flags
        cmd = self.downstream.command
        return self._format_expression(cmd, tuple([self.upstream]), flags)

    def __call__(self, *args, **kwargs):
        self.downstream(*args, **kwargs)
        return self


class ChainableBase(Expression):
    CMD = cmds.ls
    FLAGS = {}

    def __init__(self, *args, **flags):
        d = dict(**flags)
        d.update(self.FLAGS)
        d['command'] = self.CMD
        super(ChainableBase, self).__init__(*args, **d)

    @classmethod
    def can_chain(cls, other_cls):
        """
        override to provide special logic, eg for cmds.ls which has incompatible flags
        """
        return issubclass(other_cls, ChainableBase) \
               and cls.CMD == other_cls.CMD

    def compose(self, other_cls):
        downstream = other_cls()

        if self.can_chain(other_cls):
            return ChainedExpression(self, downstream)
        else:
            return DisjointExpression(self, downstream)


class LSCommand(ChainableBase):
    CMD = cmds.ls
    FLAGS = {'long': True}


class SelectionCommand(LSCommand):
    FLAGS = {'long': True, 'selection': True}


class OfTypeCommand(LSCommand):
    FLAGS = {'long': True}

    def __call__(self, *types):
        self.flags['type'] = types


class ListHistoryCommand(ChainableBase):
    CMD = cmds.listHistory


class ListRelativesCommand(ChainableBase):
    CMD = cmds.listRelatives
    FLAGS = {'fullPath': True}


class Shapes(ListRelativesCommand):
    FLAGS = {'fullPath': True, 'shapes': True}


class Parents(ListRelativesCommand):
    FLAGS = {'fullPath': True, 'parent': True}


class ComponentFilter(object):
    """
    Helper class for working with components
    """
    EXPANSIONS = {
        31: 'vtx',
        32: 'e',
        34: 'f',
        35: 'map',
        70: 'vtxFace',
        28: 'cv',
        30: 'ep'
    }

    BRACKETS = re.compile("(\[)(\d*)(\])")

    @classmethod
    def componentize(cls, comp, mask):
        if '[' in comp:
            return comp
        return "%s.%s[*]" % (comp, cls.EXPANSIONS[mask])

    @classmethod
    def expand(cls, *args, **kwargs):
        mask = kwargs.get('selectionMask')
        force = kwargs.get('force', False)

        if force:
            args = [cls.componentize(i, mask) for i in args]

        if 'force' in kwargs:
            del kwargs['force']

        result = (i for i in cmds.filterExpand(*args, **kwargs) or [])
        return result

    @classmethod
    def index(cls, item):
        return int(cls.BRACKETS.search(item).groups()[1])


class FilterExpandCommand(ChainableBase):
    CMD = ComponentFilter.expand

    def __call__(self, force=False, expand=True):
        self.flags.update(force=force, expand=expand)


class Vertices(FilterExpandCommand):
    FLAGS = {'selectionMask': 31, 'fullPath': True}


class Edges(FilterExpandCommand):
    FLAGS = {'selectionMask': 32, 'fullPath': True}


class Faces(FilterExpandCommand):
    FLAGS = {'selectionMask': 34, 'fullPath': True}


class UVs(FilterExpandCommand):
    FLAGS = {'selectionMask': 35, 'fullPath': True}


class VertexFaces(FilterExpandCommand):
    FLAGS = {'selectionMask': 70, 'fullPath': True}


class CVs(FilterExpandCommand):
    FLAGS = {'selectionMask': 28, 'fullPath': True}


class EPs(FilterExpandCommand):
    FLAGS = {'selectionMask': 30, 'fullPath': True}



class FindTypeCommand(ChainableBase):
    CMD = cmds.findType
    FLAGS = {'deep': True}


def passthru(*args, **kwargs):
    return args

class UnchainableBase(Expression):
    CMD = passthru
    FLAGS = {}

    def __init__(self, *args, **flags):
        d = dict(**flags)
        d.update(self.FLAGS)
        d['command'] = self.CMD
        super(UnchainableBase, self).__init__(*args, **d)

    def compose(self, other_cls):
        downstream = other_cls()
        return DisjointExpression(self, downstream)




class ConvertComponentCommand(UnchainableBase):
    CMD = cmds.polyListComponentConversion
    FLAGS = {}

class AsFaces(ConvertComponentCommand):
    FLAGS = {'tf': True}


class AsVertices(ConvertComponentCommand):
    FLAGS = {'tv': True}


class AsEdges(ConvertComponentCommand):
    FLAGS = {'te': True}


class AsVertexFace(ConvertComponentCommand):
    FLAGS = {'tvf': True}



class Iterate(UnchainableBase):
    def __init__(self, *args, **flags):
        self.command = self._run
        self.args = args
        d = dict(**flags)
        d.update(self.FLAGS)
        self.flags = d
        self.expression = lambda p: p

    def _run(self, *args, **kwargs):
        return itertools.imap(self.expression, args)


    def _eval(self):
        return self._run(*self.args)

    def __call__(self, expr):
        self.expression = expr

    def _format_expression(self, command, args, flags):
        cmd = str(self.expression)
        arglist = []
        if len(args):
            arglist.append("\n\t*" + args.__repr__())
        if len(flags):
            arglist.append("\n\t**" + flags.__repr__())
        return "{}({})".format(cmd, ",".join(arglist))

class Where(Iterate):
    def _run(self, *args, **kwargs):
        return itertools.ifilter(self.expression, args)


class Where_Not(Iterate):
    def _run(self, *args, **kwargs):
        return itertools.ifilterfalse(self.expression, args)


class Cast(Iterate):
    def __init__(self, *args, **flags):
        self.command = self._run
        self.args = args
        self.flags = flags
        self.expression = lambda p: p

    def _run(self, *args, **kwargs):
        return itertools.imap(self.expression, args)


class Indices(Cast):
    """
    Return the indexed part of incoming components, ie 'pCube1.vtx[1]' becomes 1
    """

    def __init__(self, *args, **kwargs):
        super(Indices, self).__init__(*args, **kwargs)
        self.expression = ComponentFilter.index


class For_Each(Iterate):
    """
    return <expr> on all incoming items; equivalent to [expr(i) for i in incoming]
    """

    def _run(self, *args, **kwargs):
        return ((p, self.expression(p)) for p in args)

    def __call__(self, expr, world=True, abs=True):
        self.expression = expr
        self.flags = {'ws': world, 'a': abs}


class XformCommand(Iterate):
    '''
    Base class for commands that return transform queries
    '''
    CMD = cmds.xform
    FLAGS = {'q': True, 'ws': True, 'a': True}

    def _run(self, *args, **kwargs):
        return ((p, self.CMD(p, **self.flags)) for p in args)

    def __call__(self, world=True, abs=True):
        self.flags.update({'ws': world, 'a': abs})


class Translations(XformCommand):
    FLAGS = {'q': True, 'ws': True, 'a': True, 't': True}


class Rotations(XformCommand):
    FLAGS = {'q': True, 'ws': True, 'a': True, 'r': True}


class Scales(XformCommand):
    FLAGS = {'q': True, 'ws': True, 'a': True, 's': True}


class Pivots(XformCommand):
    FLAGS = {'q': True, 'ws': True, 'a': True, 'piv': True}


class Matrices(XformCommand):
    FLAGS = {'q': True, 'ws': True, 'matrix': True}
        
