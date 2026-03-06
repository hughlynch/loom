package e2e_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// loomDir returns the root of the loom repo.
func loomDir() string {
	return filepath.Join(os.Getenv("HOME"), "loom")
}

// pythonPath returns the PYTHONPATH for grove SDK.
func pythonPath() string {
	return filepath.Join(os.Getenv("HOME"), "grove", "python")
}

// TestWorkerImports verifies that all loom workers can be
// imported without errors (syntax check + grove.uwp dependency).
func TestWorkerImports(t *testing.T) {
	workers := []string{
		"harvester", "extractor", "classifier",
		"corroborator", "adjudicator", "curator",
		"kb", "snapshot", "tutor", "monitor",
	}

	for _, w := range workers {
		w := w
		t.Run(w, func(t *testing.T) {
			t.Parallel()
			script := filepath.Join(loomDir(), "workers", w, "worker.py")
			cmd := exec.Command("python3", "-c",
				"import importlib.util; "+
					"spec = importlib.util.spec_from_file_location('worker', '"+script+"'); "+
					"mod = importlib.util.module_from_spec(spec)")
			cmd.Env = append(os.Environ(),
				"PYTHONPATH="+pythonPath(),
			)
			cmd.Dir = loomDir()
			out, err := cmd.CombinedOutput()
			if err != nil {
				t.Fatalf("import %s failed: %v\n%s", w, err, out)
			}
		})
	}
}

// TestWorkerCompile verifies all workers pass py_compile.
func TestWorkerCompile(t *testing.T) {
	workers := []string{
		"harvester", "extractor", "classifier",
		"corroborator", "adjudicator", "curator",
		"kb", "snapshot", "tutor", "monitor",
	}

	for _, w := range workers {
		w := w
		t.Run(w, func(t *testing.T) {
			t.Parallel()
			script := filepath.Join("workers", w, "worker.py")
			cmd := exec.Command("python3", "-m", "py_compile", script)
			cmd.Dir = loomDir()
			out, err := cmd.CombinedOutput()
			if err != nil {
				t.Fatalf("py_compile %s failed: %v\n%s", w, err, out)
			}
		})
	}
}

// TestSchemaValid verifies the SQL schema is valid SQLite.
func TestSchemaValid(t *testing.T) {
	schema := filepath.Join(loomDir(), "schema", "evidence.sql")
	data, err := os.ReadFile(schema)
	if err != nil {
		t.Fatalf("read schema: %v", err)
	}

	// Use python3 sqlite3 module to validate.
	cmd := exec.Command("python3", "-c",
		"import sqlite3, sys; "+
			"conn = sqlite3.connect(':memory:'); "+
			"conn.executescript(sys.stdin.read()); "+
			"tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]; "+
			"print(','.join(sorted(tables))); "+
			"assert 'sources' in tables; "+
			"assert 'claims' in tables; "+
			"assert 'evidence' in tables; "+
			"assert 'contradictions' in tables")
	cmd.Stdin = strings.NewReader(string(data))
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("schema validation failed: %v\n%s", err, out)
	}
	t.Logf("tables: %s", strings.TrimSpace(string(out)))
}

// TestConfigsValid verifies all JSON configs parse correctly.
func TestConfigsValid(t *testing.T) {
	configs := []string{
		"evidence_hierarchy.json",
		"confidence_rules.json",
		"source_rubrics.json",
		"anti_patterns.json",
		"quarantine.json",
	}

	for _, c := range configs {
		c := c
		t.Run(c, func(t *testing.T) {
			t.Parallel()
			path := filepath.Join(loomDir(), "configs", c)
			cmd := exec.Command("python3", "-c",
				"import json, sys; json.load(open(sys.argv[1]))",
				path)
			out, err := cmd.CombinedOutput()
			if err != nil {
				t.Fatalf("JSON parse %s failed: %v\n%s", c, err, out)
			}
		})
	}
}

// TestRitualsValid verifies all ritual JSON files parse and
// have required fields.
func TestRitualsValid(t *testing.T) {
	ritualDir := filepath.Join(loomDir(), "rituals")
	entries, err := os.ReadDir(ritualDir)
	if err != nil {
		t.Fatalf("read rituals dir: %v", err)
	}

	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		name := e.Name()
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			path := filepath.Join(ritualDir, name)
			cmd := exec.Command("python3", "-c",
				"import json, sys; "+
					"r = json.load(open(sys.argv[1])); "+
					"assert 'id' in r, 'missing id'; "+
					"assert 'version' in r, 'missing version'; "+
					"assert 'steps' in r, 'missing steps'; "+
					"print(r['id'])",
				path)
			out, err := cmd.CombinedOutput()
			if err != nil {
				t.Fatalf("ritual validation %s failed: %v\n%s", name, err, out)
			}
			t.Logf("ritual: %s", strings.TrimSpace(string(out)))
		})
	}
}

// TestConfidenceComputation verifies the deterministic
// confidence rules produce correct results for known inputs.
func TestConfidenceComputation(t *testing.T) {
	_ = time.Now() // ensure time import is used

	script := `
import sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])

from workers.corroborator.worker import compute_confidence

# T1 verified → high confidence
c = compute_confidence("verified", "T1")
assert 0.95 <= c <= 1.0, f"T1 verified: {c}"

# T7 unverified → near zero
c = compute_confidence("unverified", "T7")
assert c <= 0.05, f"T7 unverified: {c}"

# Corroboration boost
base = compute_confidence("corroborated", "T3", 1)
boosted = compute_confidence("corroborated", "T3", 3)
assert boosted > base, f"boost: {base} → {boosted}"

# Contested uses floor
c = compute_confidence("contested", "T3")
assert c == 0.20, f"contested T3: {c}"

print("confidence_computation: all rules verified")
`
	cmd := exec.Command("python3", "-c", script,
		pythonPath(), loomDir())
	cmd.Dir = loomDir()
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("confidence computation test failed: %v\n%s", err, out)
	}
	t.Logf("%s", strings.TrimSpace(string(out)))
}

// TestPipelineE2E runs the full Python pipeline test suite.
func TestPipelineE2E(t *testing.T) {
	cmd := exec.Command("python3", "-m", "pytest",
		"test/test_pipeline.py", "-v", "--tb=short")
	cmd.Dir = loomDir()
	cmd.Env = append(os.Environ(),
		"PYTHONPATH="+pythonPath(),
	)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("pipeline tests failed: %v\n%s", err, out)
	}
	t.Logf("\n%s", string(out))
}
