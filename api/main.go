package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	_ "github.com/mattn/go-sqlite3"
)

type Server struct {
	db *sql.DB
}

func main() {
	dbPath := os.Getenv("DB_PATH")
	if dbPath == "" {
		dbPath = "data/events.db"
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	db, err := sql.Open("sqlite3", dbPath+"?mode=ro")
	if err != nil {
		log.Fatalf("Failed to open database: %v", err)
	}
	defer db.Close()

	srv := &Server{db: db}

	// Static files
	fs := http.FileServer(http.Dir("web/static"))
	http.Handle("/static/", http.StripPrefix("/static/", fs))

	// API routes
	http.HandleFunc("/api/agents", srv.handleAgents)
	http.HandleFunc("/api/projects", srv.handleProjects)
	http.HandleFunc("/api/events", srv.handleEvents)
	http.HandleFunc("/api/stats", srv.handleStats)

	// Pages
	http.HandleFunc("/", srv.handleIndex)
	http.HandleFunc("/team/agents", srv.handleAgentsPage)
	http.HandleFunc("/team/projects", srv.handleProjectsPage)
	http.HandleFunc("/team/alerts", srv.handleAlertsPage)

	log.Printf("🚀 Monitor API running on :%s (db=%s)", port, dbPath)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}

func (s *Server) handleAgents(w http.ResponseWriter, r *http.Request) {
	rows, err := s.db.Query(`
		SELECT agent_name, status, current_project, current_task, current_stage,
		       task_start_time, last_action_time, updated_at
		FROM agg_agent_status
		ORDER BY agent_name
	`)
	if err != nil {
		jsonError(w, err.Error(), 500)
		return
	}
	defer rows.Close()

	type Agent struct {
		Name        string  `json:"name"`
		Status      string  `json:"status"`
		Project     *string `json:"project"`
		Task        *string `json:"task"`
		Stage       *string `json:"stage"`
		TaskStart   *string `json:"task_start"`
		LastAction  *string `json:"last_action"`
		UpdatedAt   string  `json:"updated_at"`
	}

	agents := []Agent{}
	for rows.Next() {
		var a Agent
		if err := rows.Scan(&a.Name, &a.Status, &a.Project, &a.Task, &a.Stage,
			&a.TaskStart, &a.LastAction, &a.UpdatedAt); err != nil {
			continue
		}
		agents = append(agents, a)
	}

	jsonResponse(w, agents)
}

func (s *Server) handleProjects(w http.ResponseWriter, r *http.Request) {
	rows, err := s.db.Query(`
		SELECT project_id, current_stage, stage_owner, stage_enter_time,
		       total_elapsed_min, is_overtime, latest_artifact, block_reason, updated_at
		FROM agg_project_flow
		ORDER BY updated_at DESC
	`)
	if err != nil {
		jsonError(w, err.Error(), 500)
		return
	}
	defer rows.Close()

	type Project struct {
		ID          string  `json:"id"`
		Stage       string  `json:"stage"`
		Owner       *string `json:"owner"`
		EnterTime   *string `json:"enter_time"`
		ElapsedMin  int     `json:"elapsed_min"`
		IsOvertime  bool    `json:"is_overtime"`
		Artifact    *string `json:"artifact"`
		BlockReason *string `json:"block_reason"`
		UpdatedAt   string  `json:"updated_at"`
	}

	projects := []Project{}
	for rows.Next() {
		var p Project
		var isOvertime int
		if err := rows.Scan(&p.ID, &p.Stage, &p.Owner, &p.EnterTime,
			&p.ElapsedMin, &isOvertime, &p.Artifact, &p.BlockReason, &p.UpdatedAt); err != nil {
			continue
		}
		p.IsOvertime = isOvertime == 1
		projects = append(projects, p)
	}

	jsonResponse(w, projects)
}

func (s *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	agent := r.URL.Query().Get("agent")
	category := r.URL.Query().Get("category")
	limit := r.URL.Query().Get("limit")
	if limit == "" {
		limit = "100"
	}

	query := `
		SELECT event_id, event_time, agent_name, project_id, event_category, event_type,
		       severity, model, input_tokens, output_tokens, summary
		FROM event_log
		WHERE 1=1
	`
	args := []interface{}{}

	if agent != "" {
		query += " AND agent_name = ?"
		args = append(args, agent)
	}
	if category != "" {
		query += " AND event_category = ?"
		args = append(args, category)
	}

	query += " ORDER BY event_time DESC LIMIT ?"
	args = append(args, limit)

	rows, err := s.db.Query(query, args...)
	if err != nil {
		jsonError(w, err.Error(), 500)
		return
	}
	defer rows.Close()

	type Event struct {
		ID          string  `json:"id"`
		Time        string  `json:"time"`
		Agent       string  `json:"agent"`
		Project     *string `json:"project"`
		Category    string  `json:"category"`
		Type        string  `json:"type"`
		Severity    string  `json:"severity"`
		Model       *string `json:"model"`
		InputToken  int     `json:"input_tokens"`
		OutputToken int     `json:"output_tokens"`
		Summary     *string `json:"summary"`
	}

	events := []Event{}
	for rows.Next() {
		var e Event
		if err := rows.Scan(&e.ID, &e.Time, &e.Agent, &e.Project, &e.Category, &e.Type,
			&e.Severity, &e.Model, &e.InputToken, &e.OutputToken, &e.Summary); err != nil {
			continue
		}
		events = append(events, e)
	}

	jsonResponse(w, events)
}

func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	// Agent counts
	var agentTotal, agentActive int
	s.db.QueryRow("SELECT COUNT(*) FROM agg_agent_status").Scan(&agentTotal)
	s.db.QueryRow("SELECT COUNT(*) FROM agg_agent_status WHERE status='running'").Scan(&agentActive)

	// Project counts
	var projTotal, projBlocked int
	s.db.QueryRow("SELECT COUNT(*) FROM agg_project_flow").Scan(&projTotal)
	s.db.QueryRow("SELECT COUNT(*) FROM agg_project_flow WHERE block_reason IS NOT NULL AND block_reason != ''").Scan(&projBlocked)

	// Event counts (last 24h)
	var eventCount24h int
	s.db.QueryRow("SELECT COUNT(*) FROM event_log WHERE event_time > datetime('now', '-1 day')").Scan(&eventCount24h)

	// Total tokens (last 24h)
	var totalInput, totalOutput int
	s.db.QueryRow("SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM event_log WHERE event_time > datetime('now', '-1 day')").Scan(&totalInput, &totalOutput)

	jsonResponse(w, map[string]interface{}{
		"agents":        map[string]int{"total": agentTotal, "active": agentActive},
		"projects":      map[string]int{"total": projTotal, "blocked": projBlocked},
		"events_24h":    eventCount24h,
		"tokens_24h":    map[string]int{"input": totalInput, "output": totalOutput},
	})
}

// ── Page handlers (serve HTML) ──────────────────────

func (s *Server) handleIndex(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, "web/static/index.html")
}

func (s *Server) handleAgentsPage(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, "web/static/agents.html")
}

func (s *Server) handleProjectsPage(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, "web/static/projects.html")
}

func (s *Server) handleAlertsPage(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, "web/static/alerts.html")
}

// ── Helpers ────────────────────────────────────────────

func jsonResponse(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(data)
}

func jsonError(w http.ResponseWriter, msg string, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	fmt.Fprintf(w, `{"error":"%s"}`, msg)
}
