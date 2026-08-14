/-
Copyright 2026 The Formal Conjectures Authors.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-/
import Lean

/-!
The elaborator-side facts `make_comparator_workspace.py` currently gets by
reading Lean with regular expressions.

Given a module and a declaration name, this prints JSON with what the
elaborated environment knows exactly and the text layer can only guess:

- the declaration's source range, for slicing its original text;
- its binders, with names and explicitness, for the Solution adapter;
- the type of each `sorry` inside the *statement*, which is the type of an
  `answer(sorry)` slot. The generator's manifest `answer_type` field exists
  only because surface syntax does not carry this; the environment does.

Usage: lake exe comparator_facts <Module> <declaration>

The declaration may be given in full or by any whole suffix, the same rule
the Python generator uses.
-/

open Lean Meta

/-- A request matches a name in full, or by dropping any whole prefix. -/
def declares (declared : Name) (requested : String) : Bool :=
  let s := declared.toString
  s == requested || s.endsWith ("." ++ requested)

def binderJson (name : Name) (bi : BinderInfo) : Json :=
  Json.mkObj [("name", toJson name.toString), ("explicit", toJson bi.isExplicit)]

unsafe def runWithImports {α : Type} (moduleNames : Array Name)
    (actionToRun : MetaM α) : IO α := do
  initSearchPath (← getBuildDir)
  let imports := moduleNames.map fun n => { module := n }
  Lean.enableInitializersExecution
  let env ← Lean.importModules imports {} (trustLevel := 1024) (loadExts := true)
  let ctx := { fileName := "", fileMap := default }
  let (result, _) ← Core.CoreM.toIO (actionToRun.run' {} {}) ctx { env := env }
  return result

unsafe def main (args : List String) : IO UInt32 := do
  let [modName, declName] := args
    | IO.eprintln "usage: comparator_facts <Module> <declaration>"; return 1
  runWithImports #[modName.toName] do
    let env ← getEnv
    let matches_ := env.constants.toList.filterMap fun (n, _) =>
      if declares n declName && !n.isInternal then some n else none
    match matches_ with
    | [] => IO.eprintln s!"{declName} not found in {modName}"; return 1
    | _ :: _ :: _ =>
      -- The exact-name rule the Python generator uses.
      let exact := matches_.filter (·.toString == declName)
      match exact with
      | [n] => emit env n
      | _ =>
        IO.eprintln s!"{declName} is ambiguous: {matches_}"; return 1
    | [n] => emit env n
where
  emit (env : Environment) (name : Name) : MetaM UInt32 := do
    let some info := env.find? name | IO.eprintln "vanished"; return 1
    let ranges ← findDeclarationRanges? name
    -- The statement's sorries are `answer(sorry)` slots; a proof's sorry is
    -- not in the *type*, so everything found here is a slot.
    let answerTypes ← forallTelescope info.type fun _ body => do
      let mut found : Array Expr := #[]
      let rec collect (e : Expr) (acc : Array Expr) : MetaM (Array Expr) := do
        match e with
        | .app .. =>
          if e.isAppOf ``sorryAx then
            return acc.push (← inferType e)
          else
            let mut acc := acc
            for arg in e.getAppArgs do
              acc ← collect arg acc
            collect e.getAppFn acc
        | .lam _ _ b _ | .forallE _ _ b _ => collect b acc
        | .mdata _ b => collect b acc
        | _ => return acc
      found ← collect body #[]
      found.mapM fun t => do pure (toString (← ppExpr t))
    let binders ← forallTelescope info.type fun xs _ =>
      xs.mapM fun x => do
        let d ← x.fvarId!.getDecl
        pure (binderJson d.userName d.binderInfo)
    let rangeJson := match ranges with
      | some r => Json.mkObj [
          ("startLine", toJson r.range.pos.line),
          ("endLine", toJson r.range.endPos.line)]
      | none => Json.null
    IO.println <| Json.mkObj [
      ("fullName", toJson name.toString),
      ("range", rangeJson),
      ("binders", toJson binders.toList),
      ("answerTypes", toJson answerTypes.toList)]
    return 0
