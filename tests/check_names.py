#!/usr/bin/env python3
"""Static undefined-name check for a Blender addon package.

py_compile only validates syntax, so a call to a function that was deleted
compiles cleanly and fails at runtime with NameError. This walks each module,
builds the set of names legitimately visible at each scope, and reports any
Name load that cannot resolve.

Usage: python3 check_names.py <package_dir>
"""

import ast
import builtins
import sys
import os

BUILTINS = set(dir(builtins))


class ScopeChecker(ast.NodeVisitor):
    def __init__(self, path, module_globals, package_exports):
        self.path = path
        self.module_globals = module_globals
        self.package_exports = package_exports
        self.scopes = []
        self.problems = []

    # -- scope helpers ------------------------------------------------

    def visible(self, name):
        if name in BUILTINS or name in self.module_globals:
            return True
        return any(name in scope for scope in self.scopes)

    def bind(self, name):
        if self.scopes:
            self.scopes[-1].add(name)
        else:
            self.module_globals.add(name)

    def bind_target(self, node):
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                self.bind(child.id)

    # -- collect names bound anywhere inside a function body ----------

    @staticmethod
    def collect_bindings(body):
        bound = set()
        for node in body:
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                    bound.add(child.id)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    bound.add(child.name)
                elif isinstance(child, (ast.Import, ast.ImportFrom)):
                    for alias in child.names:
                        bound.add(alias.asname or alias.name.split('.')[0])
                elif isinstance(child, ast.ExceptHandler) and child.name:
                    bound.add(child.name)
                elif isinstance(child, (ast.Global, ast.Nonlocal)):
                    bound.update(child.names)
        return bound

    # -- visitors -----------------------------------------------------

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(default)

        scope = set()
        args = node.args
        for arg in args.posonlyargs + args.args + args.kwonlyargs:
            scope.add(arg.arg)
        if args.vararg:
            scope.add(args.vararg.arg)
        if args.kwarg:
            scope.add(args.kwarg.arg)
        scope |= self.collect_bindings(node.body)

        self.scopes.append(scope)
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()
        self.bind(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        scope = self.collect_bindings(node.body)
        self.scopes.append(scope)
        for statement in node.body:
            self.visit(statement)
        self.scopes.pop()
        self.bind(node.name)

    def visit_Lambda(self, node):
        scope = set()
        args = node.args
        for arg in args.posonlyargs + args.args + args.kwonlyargs:
            scope.add(arg.arg)
        self.scopes.append(scope)
        self.visit(node.body)
        self.scopes.pop()

    def visit_comprehension_scope(self, node):
        scope = set()
        for generator in node.generators:
            for child in ast.walk(generator.target):
                if isinstance(child, ast.Name):
                    scope.add(child.id)
        self.scopes.append(scope)
        self.generic_visit(node)
        self.scopes.pop()

    visit_ListComp = visit_comprehension_scope
    visit_SetComp = visit_comprehension_scope
    visit_DictComp = visit_comprehension_scope
    visit_GeneratorExp = visit_comprehension_scope

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and not self.visible(node.id):
            self.problems.append((node.lineno, node.col_offset, node.id))
        elif isinstance(node.ctx, ast.Store):
            self.bind(node.id)


def module_globals_of(tree, path, package_exports):
    names = {'__name__', '__file__', '__package__', '__doc__', '__builtins__'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    for node in tree.body:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
    return names


def check_cross_module_imports(package_dir, modules):
    """Verify `from .mod import name` actually resolves."""
    problems = []
    exports = {}
    for name, path in modules.items():
        tree = ast.parse(open(path).read(), path)
        exports[name] = module_globals_of(tree, path, {})
    for name, path in modules.items():
        tree = ast.parse(open(path).read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module in exports:
                for alias in node.names:
                    if alias.name not in exports[node.module]:
                        problems.append(
                            f"{os.path.basename(path)}:{node.lineno} "
                            f"from .{node.module} import {alias.name} -> not defined in {node.module}.py"
                        )
    return problems


def main(package_dir):
    modules = {}
    for entry in sorted(os.listdir(package_dir)):
        if entry.endswith('.py'):
            modules[entry[:-3] if entry != '__init__.py' else '__init__'] = os.path.join(package_dir, entry)

    failures = 0

    for problem in check_cross_module_imports(package_dir, modules):
        print(f"IMPORT  {problem}")
        failures += 1

    for name, path in sorted(modules.items()):
        source = open(path).read()
        tree = ast.parse(source, path)
        globals_ = module_globals_of(tree, path, {})
        checker = ScopeChecker(path, globals_, {})
        for statement in tree.body:
            checker.visit(statement)
        lines = source.splitlines()
        for lineno, col, ident in checker.problems:
            snippet = lines[lineno - 1].strip() if lineno <= len(lines) else ''
            print(f"NAME    {os.path.basename(path)}:{lineno}: undefined name '{ident}'")
            print(f"        {snippet}")
            failures += 1

    if failures:
        print(f"\n{failures} problem(s) found.")
        return 1

    print(f"OK: {len(modules)} module(s), no undefined names, all relative imports resolve.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
