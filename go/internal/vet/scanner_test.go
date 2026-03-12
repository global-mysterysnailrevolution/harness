package vet

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/global-mysterysnailrevolution/harness/internal/config"
)

func TestSecretScanDetectsAWSKey(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "secrets.txt")
	content := `
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AKIAIOSFODNN7EXAMPLE
`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewSecretScanScanner()
	if !scanner.Available() {
		t.Fatal("secret scan should always be available")
	}

	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) < 2 {
		t.Errorf("expected at least 2 findings, got %d", len(findings))
	}

	foundAWSAccessKey := false
	foundAWSSecretKey := false
	for _, f := range findings {
		if f.Rule == "AWS Access Key" {
			foundAWSAccessKey = true
		}
		if f.Rule == "AWS Secret Key" {
			foundAWSSecretKey = true
		}
	}
	if !foundAWSAccessKey {
		t.Error("expected to detect AWS Access Key")
	}
	if !foundAWSSecretKey {
		t.Error("expected to detect AWS Secret Key")
	}
}

func TestSecretScanDetectsPrivateKey(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "key.pem")
	content := `-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA1234567890
-----END RSA PRIVATE KEY-----`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewSecretScanScanner()
	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) == 0 {
		t.Error("expected to detect private key")
	}

	found := false
	for _, f := range findings {
		if f.Rule == "Private Key Block" {
			found = true
			if f.Severity != SevCritical {
				t.Errorf("expected critical severity, got %s", f.Severity)
			}
		}
	}
	if !found {
		t.Error("expected Private Key Block finding")
	}
}

func TestSecretScanDetectsJWT(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "config.js")
	content := `const token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewSecretScanScanner()
	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Rule == "JWT Token" {
			found = true
		}
	}
	if !found {
		t.Error("expected to detect JWT token")
	}
}

func TestSecretScanDetectsGitHubToken(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "env.txt")
	content := `GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewSecretScanScanner()
	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Rule == "GitHub Token" {
			found = true
		}
	}
	if !found {
		t.Error("expected to detect GitHub token")
	}
}

func TestSecretScanSkipsBinaryFiles(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "program.exe")
	if err := os.WriteFile(testFile, []byte("AKIAIOSFODNN7EXAMPLE"), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewSecretScanScanner()
	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) != 0 {
		t.Errorf("expected 0 findings for binary file, got %d", len(findings))
	}
}

func TestPathTraversalDetection(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "handler.js")
	content := `
const filePath = req.query.file;
const fullPath = path.join(uploadDir, '../../../etc/passwd');
const encoded = '%2e%2e%2fpasswd';
`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewPathTraversalScanner()
	if !scanner.Available() {
		t.Fatal("path traversal scanner should always be available")
	}

	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	if len(findings) < 2 {
		t.Errorf("expected at least 2 findings, got %d", len(findings))
	}

	foundDotDot := false
	foundEncoded := false
	for _, f := range findings {
		if f.Rule == "dot-dot-slash traversal" {
			foundDotDot = true
		}
		if f.Rule == "URL-encoded traversal" {
			foundEncoded = true
		}
	}
	if !foundDotDot {
		t.Error("expected dot-dot-slash finding")
	}
	if !foundEncoded {
		t.Error("expected URL-encoded traversal finding")
	}
}

func TestPathTraversalNullByte(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "code.py")
	content := `filename = input + "%00.jpg"`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	scanner := NewPathTraversalScanner()
	findings, err := scanner.Scan(context.Background(), dir)
	if err != nil {
		t.Fatal(err)
	}

	found := false
	for _, f := range findings {
		if f.Rule == "null byte injection" {
			found = true
		}
	}
	if !found {
		t.Error("expected null byte injection finding")
	}
}

func TestPipelineWithBuiltins(t *testing.T) {
	dir := t.TempDir()
	testFile := filepath.Join(dir, "secrets.py")
	content := `
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
path = "../../../etc/passwd"
`
	if err := os.WriteFile(testFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	pipeline := NewPipeline(
		config.VettingPolicy{
			Scanners:       []string{"secretscan", "pathtraversal"},
			FailThresholds: map[string]int{"critical": 0, "high": 3},
		},
		map[string]string{},
	)

	report, err := pipeline.Run(context.Background(), dir, []string{"secretscan", "pathtraversal"})
	if err != nil {
		t.Fatal(err)
	}

	if len(report.Scanners) != 2 {
		t.Errorf("expected 2 scanners run, got %d: %v", len(report.Scanners), report.Scanners)
	}

	if len(report.Findings) == 0 {
		t.Error("expected findings from built-in scanners")
	}
}
