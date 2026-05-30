use std::env;
use std::error::Error;
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

type CliResult<T> = Result<T, Box<dyn Error>>;

const MARKET_ACTIONS: &[&str] = &[
    "ticker",
    "tickers",
    "orderbook",
    "candles",
    "instruments",
    "funding-rate",
    "mark-price",
    "trades",
    "index-ticker",
    "index-candles",
    "price-limit",
    "open-interest",
    "stock-tokens",
    "instruments-by-category",
    "filter",
    "oi-history",
    "oi-change",
    "pair-spread",
];

const READ_ONLY_ACTIONS: &[(&str, &[&str])] = &[
    ("market", MARKET_ACTIONS),
    (
        "account",
        &[
            "balance",
            "asset-balance",
            "positions",
            "positions-history",
            "bills",
            "fees",
            "config",
            "max-size",
            "max-avail-size",
            "max-withdrawal",
            "audit",
        ],
    ),
    ("spot", &["orders", "get", "fills"]),
    (
        "swap",
        &["positions", "orders", "get", "fills", "get-leverage"],
    ),
    (
        "futures",
        &["positions", "orders", "get", "fills", "get-leverage"],
    ),
    (
        "option",
        &[
            "orders",
            "get",
            "positions",
            "fills",
            "instruments",
            "greeks",
        ],
    ),
];

const MUTATING_ACTIONS: &[(&str, &[&str])] = &[
    ("account", &["set-position-mode", "transfer"]),
    ("spot", &["place", "amend", "cancel", "batch", "leverage"]),
    (
        "swap",
        &["place", "amend", "cancel", "batch", "close", "leverage"],
    ),
    (
        "futures",
        &["place", "amend", "cancel", "batch", "close", "leverage"],
    ),
    ("option", &["place", "amend", "cancel", "batch-cancel"]),
];

const BLOCKED_MODULES: &[&str] = &[
    "earn",
    "bot",
    "event",
    "smartmoney",
    "setup",
    "pilot",
    "skill",
    "upgrade",
];
const BLOCKED_ARG_TOKENS: &[&str] = &["--live", "--demo", "--json", "--env", "--profile"];

#[derive(Debug)]
struct GuardThresholds {
    hard_stop_drawdown_pct: f64,
    caution_drawdown_pct: f64,
    hard_stop_consecutive_losses: i64,
    caution_consecutive_losses: i64,
    min_minutes_between_trades_after_loss: i64,
}

impl Default for GuardThresholds {
    fn default() -> Self {
        Self {
            hard_stop_drawdown_pct: -3.0,
            caution_drawdown_pct: -1.5,
            hard_stop_consecutive_losses: 3,
            caution_consecutive_losses: 2,
            min_minutes_between_trades_after_loss: 30,
        }
    }
}

#[derive(Debug)]
struct TradingState {
    drawdown_pct: f64,
    consecutive_losses: i64,
    minutes_since_last_trade: Option<i64>,
    planned_trade_has_written_thesis: bool,
}

#[derive(Debug)]
struct GuardDecision {
    level: String,
    trade_allowed: bool,
    reasons: Vec<String>,
    required_actions: Vec<String>,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("finharness_error={err}");
        std::process::exit(1);
    }
}

fn run() -> CliResult<()> {
    let mut args: Vec<String> = env::args().skip(1).collect();
    let Some(command) = args.first().cloned() else {
        print_usage();
        return Ok(());
    };
    args.remove(0);

    match command.as_str() {
        "guard" => run_guard(&args),
        "okx" => run_okx(&args),
        "receipt" => run_receipt(&args),
        "version" => {
            println!("finharness-cli {}", env!("CARGO_PKG_VERSION"));
            Ok(())
        }
        _ => {
            print_usage();
            Err(format!("unknown command: {command}").into())
        }
    }
}

fn print_usage() {
    eprintln!(
        "Usage:
  finharness-cli guard [--drawdown-pct N] [--consecutive-losses N] [--minutes-since-last-trade N] [--thesis]
  finharness-cli okx --live|--demo <module> <action> [args...]
  finharness-cli receipt --kind KIND --symbol SYMBOL --status STATUS"
    );
}

fn run_guard(args: &[String]) -> CliResult<()> {
    if args.iter().any(|a| a == "--interactive") {
        return run_guard_interactive();
    }

    let mut state = TradingState {
        drawdown_pct: 0.0,
        consecutive_losses: 0,
        minutes_since_last_trade: None,
        planned_trade_has_written_thesis: false,
    };

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--drawdown-pct" => {
                state.drawdown_pct = parse_next(args, &mut i, "--drawdown-pct")?.parse()?;
            }
            "--consecutive-losses" => {
                state.consecutive_losses =
                    parse_next(args, &mut i, "--consecutive-losses")?.parse()?;
            }
            "--minutes-since-last-trade" => {
                state.minutes_since_last_trade =
                    Some(parse_next(args, &mut i, "--minutes-since-last-trade")?.parse()?);
            }
            "--thesis" => {
                state.planned_trade_has_written_thesis = true;
            }
            other => return Err(format!("unknown guard arg: {other}").into()),
        }
        i += 1;
    }

    let decision = evaluate_trading_state(&state, &GuardThresholds::default());
    println!("{}", guard_json(&decision));
    Ok(())
}

fn run_guard_interactive() -> CliResult<()> {
    use std::io::{self, Write};

    let mut stdin = io::stdin();
    let mut stdout = io::stdout();
    let mut buf = String::new();

    macro_rules! ask {
        ($prompt:expr, $var:ident, $type:ty) => {
            loop {
                print!($prompt);
                stdout.flush()?;
                buf.clear();
                stdin.read_line(&mut buf)?;
                match buf.trim().parse::<$type>() {
                    Ok(v) => {
                        $var = v;
                        break;
                    }
                    Err(_) => eprintln!("  Invalid input, try again."),
                }
            }
        };
    }

    let entry: f64;
    let stop: f64;
    let equity: f64;
    let risk_pct: f64 = 2.0;

    println!("=== Pre-Trade Guard ===\n");

    ask!("Entry price:         ", entry, f64);
    ask!("Stop-loss price:     ", stop, f64);
    ask!("Account equity ($):  ", equity, f64);

    let is_long = entry > stop;
    let r_distance = if is_long {
        (entry - stop).abs()
    } else {
        (stop - entry).abs()
    };
    let one_r_pct = (r_distance / entry) * 100.0;
    let max_risk_dollars = equity * (risk_pct / 100.0);
    let max_position_size = max_risk_dollars / r_distance;
    let max_position_pct = (max_position_size * entry / equity) * 100.0;

    println!();
    println!("--- Position Sizing ---");
    println!("  Direction:     {}", if is_long { "LONG" } else { "SHORT" });
    println!("  1R distance:   ${:.2} ({:.2}%)", r_distance, one_r_pct);
    println!("  Max risk ({}%): ${:.2}", risk_pct, max_risk_dollars);
    println!("  Max position:   {:.4} units", max_position_size);
    println!("  Position value: ${:.2} ({:.1}% of equity)", max_position_size * entry, max_position_pct);

    println!();
    println!("--- Rule Check ---");

    let mut passed = true;

    if r_distance <= 0.0 {
        println!("  FAIL: Entry and stop must differ.");
        passed = false;
    }

    if one_r_pct > 5.0 {
        println!("  WARN: 1R > 5% of price — wide stop may indicate poor entry.");
    }

    if max_risk_dollars <= 0.0 {
        println!("  FAIL: Invalid equity or risk parameters.");
        passed = false;
    }

    if max_position_size <= 0.0 {
        println!("  FAIL: Cannot calculate position size.");
        passed = false;
    }

    if max_position_pct > 50.0 {
        println!("  WARN: Position > 50% of equity — consider reducing.");
    }

    println!();
    println!("--- Thesis ---");
    println!("  What invalidation would prove this trade wrong?");
    print!("  > ");
    stdout.flush()?;
    buf.clear();
    stdin.read_line(&mut buf)?;
    let thesis = buf.trim().to_string();

    if thesis.is_empty() {
        println!("  FAIL: No written thesis.");
        passed = false;
    } else {
        println!("  Thesis recorded.");
    }

    println!();
    if passed {
        println!("RESULT: TRADE ALLOWED");
        println!("  Max size: {:.4} units (${:.2})", max_position_size, max_position_size * entry);
        println!("  Max risk: ${:.2} ({}% of equity)", max_risk_dollars, risk_pct);
        println!("  Invalidation: {}", thesis);
    } else {
        println!("RESULT: TRADE BLOCKED");
        println!("  Fix the issues above before re-submitting.");
    }

    Ok(())
}

fn parse_next<'a>(args: &'a [String], i: &mut usize, flag: &str) -> CliResult<&'a str> {
    *i += 1;
    args.get(*i)
        .map(String::as_str)
        .ok_or_else(|| format!("missing value for {flag}").into())
}

fn evaluate_trading_state(state: &TradingState, thresholds: &GuardThresholds) -> GuardDecision {
    let mut reasons = Vec::new();
    let mut actions = Vec::new();
    let mut hard_stop = false;
    let mut caution = false;

    if state.drawdown_pct <= thresholds.hard_stop_drawdown_pct {
        hard_stop = true;
        reasons.push(format!(
            "drawdown {:.2}% breached hard stop {:.2}%",
            state.drawdown_pct, thresholds.hard_stop_drawdown_pct
        ));
    } else if state.drawdown_pct <= thresholds.caution_drawdown_pct {
        caution = true;
        reasons.push(format!(
            "drawdown {:.2}% breached caution {:.2}%",
            state.drawdown_pct, thresholds.caution_drawdown_pct
        ));
    }

    if state.consecutive_losses >= thresholds.hard_stop_consecutive_losses {
        hard_stop = true;
        reasons.push(format!(
            "{} consecutive losses breached hard stop {}",
            state.consecutive_losses, thresholds.hard_stop_consecutive_losses
        ));
    } else if state.consecutive_losses >= thresholds.caution_consecutive_losses {
        caution = true;
        reasons.push(format!(
            "{} consecutive losses breached caution {}",
            state.consecutive_losses, thresholds.caution_consecutive_losses
        ));
    }

    if let Some(minutes) = state.minutes_since_last_trade {
        if state.consecutive_losses > 0
            && minutes < thresholds.min_minutes_between_trades_after_loss
        {
            caution = true;
            reasons.push(format!(
                "only {minutes} minutes since a losing trade; minimum is {}",
                thresholds.min_minutes_between_trades_after_loss
            ));
        }
    }

    if !state.planned_trade_has_written_thesis {
        caution = true;
        reasons.push("planned trade has no written thesis".to_string());
    }

    if hard_stop {
        actions.extend([
            "Stop opening new trades for the rest of the session.".to_string(),
            "Cancel non-essential pending orders.".to_string(),
            "Write a loss review before considering the next session.".to_string(),
            "Reduce the next session to demo or read-only observation.".to_string(),
        ]);
        return GuardDecision {
            level: "hard_stop".to_string(),
            trade_allowed: false,
            reasons,
            required_actions: actions,
        };
    }

    if caution {
        actions.extend([
            "Wait through the cooldown before any new trade.".to_string(),
            "Write entry, invalidation, size, and max loss before acting.".to_string(),
            "Use smaller size or demo mode until execution quality normalizes.".to_string(),
        ]);
        return GuardDecision {
            level: "caution".to_string(),
            trade_allowed: false,
            reasons,
            required_actions: actions,
        };
    }

    GuardDecision {
        level: "clear".to_string(),
        trade_allowed: true,
        reasons: vec!["within configured behavioral risk limits".to_string()],
        required_actions: vec![
            "Continue to use predefined size and invalidation rules.".to_string(),
        ],
    }
}

fn guard_json(decision: &GuardDecision) -> String {
    format!(
        "{{\n  \"level\": \"{}\",\n  \"trade_allowed\": {},\n  \"reasons\": {},\n  \"required_actions\": {}\n}}",
        escape_json(&decision.level),
        decision.trade_allowed,
        string_array_json(&decision.reasons),
        string_array_json(&decision.required_actions)
    )
}

fn run_okx(args: &[String]) -> CliResult<()> {
    let mut live = false;
    let mut demo = false;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--live" => live = true,
            "--demo" => demo = true,
            _ => break,
        }
        i += 1;
    }
    if live && demo {
        return Err("--live and --demo are mutually exclusive".into());
    }
    let module = args.get(i).ok_or("missing OKX module")?;
    let action = args.get(i + 1).ok_or("missing OKX action")?;
    let okx_args = &args[(i + 2)..];

    if BLOCKED_MODULES.contains(&module.as_str()) {
        return Err(format!("blocked OKX module: {module}").into());
    }
    for token in okx_args {
        if BLOCKED_ARG_TOKENS.contains(&token.as_str()) {
            return Err(format!("blocked OKX arg token: {token}").into());
        }
    }

    let read_only = action_allowed(READ_ONLY_ACTIONS, module, action);
    let mutating = action_allowed(MUTATING_ACTIONS, module, action);
    if !read_only && !mutating {
        return Err(format!("blocked OKX command: {module} {action}").into());
    }
    if mutating
        && live
        && env::var("FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS")
            .ok()
            .as_deref()
            != Some("1")
    {
        return Err("live mutation requires FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1".into());
    }

    let mut command_args: Vec<OsString> = vec!["--json".into()];
    if live {
        command_args.push("--live".into());
    }
    if demo {
        command_args.push("--demo".into());
    }
    command_args.push(module.into());
    command_args.push(action.into());
    command_args.extend(okx_args.iter().map(OsString::from));

    let output = Command::new("okx")
        .args(command_args)
        .stdin(Stdio::null())
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "okx failed with {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        )
        .into());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    print!("{}", redact_okx_output(&stdout));
    Ok(())
}

fn action_allowed(table: &[(&str, &[&str])], module: &str, action: &str) -> bool {
    table
        .iter()
        .find(|(candidate, _)| *candidate == module)
        .is_some_and(|(_, actions)| actions.contains(&action))
}

fn run_receipt(args: &[String]) -> CliResult<()> {
    let mut kind = "manual";
    let mut symbol = "NA";
    let mut status = "unknown";

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--kind" => kind = parse_next(args, &mut i, "--kind")?,
            "--symbol" => symbol = parse_next(args, &mut i, "--symbol")?,
            "--status" => status = parse_next(args, &mut i, "--status")?,
            other => return Err(format!("unknown receipt arg: {other}").into()),
        }
        i += 1;
    }

    let now = unix_seconds()?;
    let dir = PathBuf::from("data/receipts/rust");
    fs::create_dir_all(&dir)?;
    let path = dir.join(format!("{now}-{kind}-{symbol}.json"));
    let body = format!(
        "{{\n  \"timestamp_unix\": {now},\n  \"kind\": \"{}\",\n  \"symbol\": \"{}\",\n  \"status\": \"{}\",\n  \"writer\": \"finharness-cli\"\n}}\n",
        escape_json(kind),
        escape_json(symbol),
        escape_json(status)
    );
    fs::write(&path, body)?;
    println!("{}", path.display());
    Ok(())
}

fn unix_seconds() -> CliResult<u64> {
    Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())
}

fn string_array_json(values: &[String]) -> String {
    let inner = values
        .iter()
        .map(|value| format!("\"{}\"", escape_json(value)))
        .collect::<Vec<_>>()
        .join(", ");
    format!("[{inner}]")
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

fn redact_okx_output(output: &str) -> String {
    let mut redacted = output.to_string();
    for key in ["uid", "mainUid", "ip", "label"] {
        redacted = redact_json_string_field(&redacted, key);
    }
    redacted
}

fn redact_json_string_field(input: &str, key: &str) -> String {
    let pattern = format!("\"{key}\":");
    let mut output = String::with_capacity(input.len());
    let mut cursor = 0;

    while let Some(relative) = input[cursor..].find(&pattern) {
        let start = cursor + relative;
        output.push_str(&input[cursor..start + pattern.len()]);
        let mut value_start = start + pattern.len();
        while input[value_start..].starts_with(' ') {
            output.push(' ');
            value_start += 1;
        }

        if !input[value_start..].starts_with('"') {
            cursor = value_start;
            continue;
        }

        output.push('"');
        output.push_str("[redacted]");
        output.push('"');

        let mut value_end = value_start + 1;
        let bytes = input.as_bytes();
        let mut escaped = false;
        while value_end < input.len() {
            let byte = bytes[value_end];
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                value_end += 1;
                break;
            }
            value_end += 1;
        }
        cursor = value_end;
    }

    output.push_str(&input[cursor..]);
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn guard_hard_stops_on_drawdown_and_losses() {
        let decision = evaluate_trading_state(
            &TradingState {
                drawdown_pct: -3.0,
                consecutive_losses: 3,
                minutes_since_last_trade: Some(999),
                planned_trade_has_written_thesis: true,
            },
            &GuardThresholds::default(),
        );

        assert_eq!(decision.level, "hard_stop");
        assert!(!decision.trade_allowed);
        assert_eq!(decision.reasons.len(), 2);
    }

    #[test]
    fn guard_requires_written_thesis() {
        let decision = evaluate_trading_state(
            &TradingState {
                drawdown_pct: 0.0,
                consecutive_losses: 0,
                minutes_since_last_trade: Some(999),
                planned_trade_has_written_thesis: false,
            },
            &GuardThresholds::default(),
        );

        assert_eq!(decision.level, "caution");
        assert!(!decision.trade_allowed);
        assert!(
            decision
                .reasons
                .contains(&"planned trade has no written thesis".to_string())
        );
    }

    #[test]
    fn okx_action_tables_classify_read_and_write() {
        assert!(action_allowed(READ_ONLY_ACTIONS, "account", "balance"));
        assert!(action_allowed(READ_ONLY_ACTIONS, "swap", "positions"));
        assert!(action_allowed(MUTATING_ACTIONS, "swap", "place"));
        assert!(!action_allowed(READ_ONLY_ACTIONS, "swap", "place"));
    }

    #[test]
    fn redacts_sensitive_okx_fields() {
        let raw = r#"[{"uid":"123","mainUid":"456","ip":"1.2.3.4","label":"me","acctLv":"2"}]"#;
        let redacted = redact_okx_output(raw);

        assert!(redacted.contains(r#""uid":"[redacted]""#));
        assert!(redacted.contains(r#""mainUid":"[redacted]""#));
        assert!(redacted.contains(r#""ip":"[redacted]""#));
        assert!(redacted.contains(r#""label":"[redacted]""#));
        assert!(redacted.contains(r#""acctLv":"2""#));
        assert!(!redacted.contains("123"));
        assert!(!redacted.contains("456"));
    }
}
