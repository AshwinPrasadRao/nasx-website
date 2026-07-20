-- Post Navigation Lua Filter
-- Adds previous/next navigation to blogs and publications

local stringify = require("pandoc.utils").stringify

-- Helper function to read file contents
local function read_file(path)
  local file = io.open(path, "r")
  if not file then return nil end
  local content = file:read("*all")
  file:close()
  return content
end

-- Helper function to extract YAML front matter
local function extract_yaml(content)
  -- Normalize line endings (handle \r\n, \r, and \n)
  content = content:gsub("\r\n", "\n"):gsub("\r", "\n")

  local yaml_start, yaml_end = content:find("^%-%-%-\n")
  if not yaml_start then
    return nil
  end

  local _, close_pos = content:find("\n%-%-%-", yaml_end)
  if not close_pos then
    return nil
  end

  return content:sub(yaml_end + 1, close_pos - 4)
end

-- Helper function to extract date from YAML
local function extract_date(yaml)
  if not yaml then return nil end
  local date = yaml:match('date:%s*["\']?([%d%-]+)["\']?')
  return date
end

-- Helper function to extract title from YAML
local function extract_title(yaml)
  if not yaml then return nil end
  -- Try quoted title first
  local title = yaml:match('title:%s*"([^"]+)"')
  if not title then
    title = yaml:match("title:%s*'([^']+)'")
  end
  if not title then
    -- Unquoted title - get until end of line
    title = yaml:match('title:%s*([^\n]+)')
    if title then
      title = title:gsub("^%s+", ""):gsub("%s+$", "")
    end
  end
  return title
end

-- Helper function to list files in directory
local function list_files(dir, extension)
  local files = {}
  -- Try Unix ls first
  local handle = io.popen('ls -1 "' .. dir .. '" 2>/dev/null')
  if handle then
    for file in handle:lines() do
      if file:match("%." .. extension .. "$") then
        table.insert(files, file)
      end
    end
    handle:close()
  end
  -- Fall back to Windows dir if nothing found
  if #files == 0 then
    local win_dir = dir:gsub("/", "\\")
    handle = io.popen('dir /b "' .. win_dir .. '" 2>nul')
    if handle then
      for file in handle:lines() do
        if file:match("%." .. extension .. "$") then
          table.insert(files, file)
        end
      end
      handle:close()
    end
  end
  return files
end

-- Helper function to get content type and base path from input file
local function get_content_info(input_file)
  -- Handle both absolute and relative paths
  -- Check for content/blogs or content/publications pattern
  if input_file:match("content/blogs/") then
    local base_path = input_file:match("(.*/content/blogs/)") or input_file:match("(content/blogs/)")
    return "blog", base_path
  elseif input_file:match("content/publications/") then
    local base_path = input_file:match("(.*/content/publications/)") or input_file:match("(content/publications/)")
    return "publication", base_path
  elseif input_file:match("content/trackers/westasianwar/bulletins/") then
    local base_path = input_file:match("(.*/content/trackers/westasianwar/bulletins/)") or input_file:match("(content/trackers/westasianwar/bulletins/)")
    return "bulletin", base_path
  end
  return nil, nil
end

-- Build navigation HTML
local function build_navigation_html(prev_post, next_post, content_type)
  local listing_url, listing_text
  if content_type == "blog" then
    listing_url = "/pages/blogs/"
    listing_text = "All Blogs"
  elseif content_type == "bulletin" then
    listing_url = "/pages/trackers/westasianwar/"
    listing_text = "Live Dossier"
  else
    listing_url = "/pages/publications/"
    listing_text = "All Publications"
  end

  local html = [[
<nav class="post-navigation" aria-label="Post navigation">
  <div class="nav-links">
]]

  -- Previous post link (newer post)
  if prev_post then
    html = html .. string.format([[
    <a href="%s" class="nav-prev" rel="prev">
      <span class="nav-label">&larr; Previous</span>
      <span class="nav-title">%s</span>
    </a>
]], prev_post.url, prev_post.title or "Previous Post")
  else
    html = html .. [[
    <div class="nav-prev nav-placeholder"></div>
]]
  end

  -- Back to listing link
  html = html .. string.format([[
    <a href="%s" class="nav-listing">
      <span class="nav-listing-icon">&#9776;</span>
      <span class="nav-listing-text">%s</span>
    </a>
]], listing_url, listing_text)

  -- Next post link (older post)
  if next_post then
    html = html .. string.format([[
    <a href="%s" class="nav-next" rel="next">
      <span class="nav-label">Next &rarr;</span>
      <span class="nav-title">%s</span>
    </a>
]], next_post.url, next_post.title or "Next Post")
  else
    html = html .. [[
    <div class="nav-next nav-placeholder"></div>
]]
  end

  html = html .. [[
  </div>
</nav>
]]

  return html
end

-- Main filter function
function Pandoc(doc)
  -- Get the original source file from Quarto
  local input_file = nil

  -- Try to get the input file from quarto.doc.input_file (Quarto 1.3+)
  if quarto and quarto.doc and quarto.doc.input_file then
    input_file = quarto.doc.input_file
  end

  if not input_file then
    return doc
  end

  -- Normalise path separators to forward slashes (Windows compatibility)
  input_file = input_file:gsub("\\", "/")

  -- Get content type and base path
  local content_type, base_path = get_content_info(input_file)

  if not content_type or not base_path then
    return doc
  end

  -- Get current file name
  local current_file = input_file:match("([^/]+)$")

  -- List all QMD files in the directory
  local files = list_files(base_path, "qmd")

  -- If no files found, return
  if #files == 0 then
    return doc
  end

  -- Build list of posts with dates
  local posts = {}
  for _, file in ipairs(files) do
    if file ~= "index.qmd" and file ~= "_metadata.yml" then
      local filepath = base_path .. file
      local content = read_file(filepath)
      if content then
        local yaml = extract_yaml(content)
        local date = extract_date(yaml)
        local title = extract_title(yaml)

        if date then
          -- Generate URL - use the actual filename slug
          local url_slug = file:gsub("%.qmd$", "")
          local url
          if content_type == "bulletin" then
            url = "/content/trackers/westasianwar/bulletins/" .. url_slug .. ".html"
          else
            url = "/content/" .. (content_type == "blog" and "blogs/" or "publications/") .. url_slug .. ".html"
          end

          table.insert(posts, {
            file = file,
            date = date,
            title = title,
            url = url
          })
        end
      end
    end
  end

  -- Sort posts by date (descending - newest first)
  table.sort(posts, function(a, b)
    return a.date > b.date
  end)

  -- Find current post index
  local current_index = nil
  for i, post in ipairs(posts) do
    if post.file == current_file then
      current_index = i
      break
    end
  end

  if not current_index then
    return doc
  end

  -- Get previous and next posts
  -- Since sorted descending, "prev" is newer (index - 1), "next" is older (index + 1)
  local prev_post = posts[current_index + 1]  -- Older post
  local next_post = posts[current_index - 1]  -- Newer post

  -- Build navigation HTML
  local nav_html = build_navigation_html(prev_post, next_post, content_type)

  -- Add navigation to the end of the document
  local nav_block = pandoc.RawBlock("html", nav_html)
  table.insert(doc.blocks, nav_block)

  return doc
end
