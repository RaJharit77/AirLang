//! `air` — point d'entrée unique d'AirLang.
//!
//!   air fmt [--check] [--stdout] <fichiers ou dossiers>   formate (natif, ce binaire)
//!   air run|build|check <fichier.air> [...]               délègue au compilateur (Python)
//!   air version | help
//!
//! Le compilateur est cherché via $AIR_HOME, puis en remontant depuis le binaire et le
//! répertoire courant jusqu'à un dossier contenant `compiler/__main__.py`.

mod fmt;
mod lexer;

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{exit, Command};

const VERSION: &str = env!("CARGO_PKG_VERSION");

const HELP: &str = "AirLang — simple comme respirer.

Usage :
  air run <fichier.air>        compile et exécute
  air build <fichier.air>      produit un binaire
  air check <fichier.air>      vérifie sans compiler
  air fmt [--check] [--stdout] [--no-align] <fichiers ou dossiers>
                               formate les fichiers .air (--check : ne modifie rien, code 1 si
                               un fichier n'est pas formaté ; --no-align : n'aligne pas les champs)
  air version                  affiche la version
  air help                     affiche cette aide

Les options de `run`, `build` et `check` sont celles du compilateur : `air build --help`.";

fn find_compiler_root() -> Option<PathBuf> {
    if let Ok(home) = env::var("AIR_HOME") {
        let p = PathBuf::from(home);
        if p.join("compiler").join("__main__.py").is_file() {
            return Some(p);
        }
    }
    let mut starts: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = env::current_exe() {
        starts.push(exe);
    }
    if let Ok(cwd) = env::current_dir() {
        starts.push(cwd);
    }
    for start in starts {
        let mut cur: Option<&Path> = Some(start.as_path());
        while let Some(dir) = cur {
            if dir.join("compiler").join("__main__.py").is_file() {
                return Some(dir.to_path_buf());
            }
            cur = dir.parent();
        }
    }
    None
}

fn delegate(args: &[String]) -> i32 {
    let root = match find_compiler_root() {
        Some(r) => r,
        None => {
            eprintln!("Erreur : compilateur AirLang introuvable.\n  = aide : définissez AIR_HOME vers le dossier du projet (celui qui contient `compiler/`)");
            return 2;
        }
    };
    let py = ["python3", "python"]
        .iter()
        .find(|p| Command::new(p).arg("--version").output().is_ok())
        .copied();
    let py = match py {
        Some(p) => p,
        None => {
            eprintln!("Erreur : Python 3 est requis pour compiler (installez python3).");
            return 2;
        }
    };
    match Command::new(py).args(["-m", "compiler"]).args(args).env("PYTHONPATH", &root).status() {
        Ok(s) => s.code().unwrap_or(1),
        Err(e) => {
            eprintln!("Erreur : impossible de lancer Python : {e}");
            2
        }
    }
}

fn collect(path: &Path, out: &mut Vec<PathBuf>) {
    if path.is_dir() {
        let mut entries: Vec<PathBuf> = match fs::read_dir(path) {
            Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
            Err(_) => return,
        };
        entries.sort();
        for e in entries {
            let name = e.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name.starts_with('.') || name == "target" || name == "node_modules" {
                continue;
            }
            collect(&e, out);
        }
    } else if path.extension().map_or(false, |x| x == "air") {
        out.push(path.to_path_buf());
    }
}

fn cmd_fmt(args: &[String]) -> i32 {
    let mut check = false;
    let mut to_stdout = false;
    let mut opts = fmt::Options::default();
    let mut files = Vec::new();
    for a in args {
        match a.as_str() {
            "--check" => check = true,
            "--stdout" => to_stdout = true,
            "--no-align" => opts.align_fields = false,
            s if s.starts_with("--") => {
                eprintln!("Erreur : option inconnue `{s}`\n  = aide : air fmt [--check] [--stdout] <fichiers ou dossiers>");
                return 2;
            }
            s => collect(Path::new(s), &mut files),
        }
    }
    if files.is_empty() {
        eprintln!("Erreur : aucun fichier .air à formater\n  = aide : air fmt <fichier.air | dossier>");
        return 2;
    }
    let (mut changed, mut failed) = (0, 0);
    for f in &files {
        let src = match fs::read_to_string(f) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("Erreur : lecture de {} impossible : {e}", f.display());
                failed += 1;
                continue;
            }
        };
        match fmt::format_with(&src, opts) {
            Err(e) => {
                eprintln!("{} : {e} (fichier non modifié)", f.display());
                failed += 1;
            }
            Ok(new) => {
                if to_stdout {
                    print!("{new}");
                } else if new != src {
                    changed += 1;
                    if check {
                        println!("à reformater : {}", f.display());
                    } else if let Err(e) = fs::write(f, new) {
                        eprintln!("Erreur : écriture de {} impossible : {e}", f.display());
                        failed += 1;
                    } else {
                        println!("formaté : {}", f.display());
                    }
                }
            }
        }
    }
    if failed > 0 {
        return 2;
    }
    if check && changed > 0 {
        return 1;
    }
    0
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let code = match args.first().map(String::as_str) {
        None | Some("help") | Some("-h") | Some("--help") => {
            println!("{HELP}");
            0
        }
        Some("version") | Some("--version") | Some("-V") => {
            println!("air {VERSION}");
            0
        }
        Some("fmt") => cmd_fmt(&args[1..]),
        Some("run") | Some("build") | Some("check") | Some("tokens") | Some("ast") => delegate(&args),
        Some(other) if other.ends_with(".air") => delegate(&args),
        Some(other) => {
            eprintln!("Erreur : commande inconnue `{other}`\n  = aide : `air help` liste les commandes");
            2
        }
    };
    exit(code);
}
