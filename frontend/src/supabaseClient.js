import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim();
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();

export const supabaseConfigError =
  !supabaseUrl || !supabaseAnonKey
    ? "Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to frontend/.env, then restart the dev server."
    : null;

export const supabase = supabaseConfigError
  ? null
  : createClient(supabaseUrl, supabaseAnonKey, {
      db: { schema: "marts" },
    });
