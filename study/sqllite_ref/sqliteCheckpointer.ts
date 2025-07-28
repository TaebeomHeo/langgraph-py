import { SqliteSaver } from "@langchain/langgraph-checkpoint-sqlite";
import Database, { Options } from "better-sqlite3";
import { join, dirname } from 'path';
import fs from 'fs';
import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// Constants
const DB_DIR = join(process.cwd(), 'data');
const DEFAULT_DB_PATH = join(DB_DIR, 'checkpoints.db');
const SQLITE_DB_PATH = process.env.SQLITE_DB_PATH ?? DEFAULT_DB_PATH;

export const initializeCheckpointer = (): SqliteSaver => {
    // 디렉토리 생성
    const dir = dirname(SQLITE_DB_PATH);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }

    // 데이터베이스 연결
    const db = new Database(SQLITE_DB_PATH, {
        verbose: (message: string) => {
            // console.log(message);
        }
    } as Options);

    // SQLiteSaver 인스턴스 생성 및 반환
    return new SqliteSaver(db);
}; 