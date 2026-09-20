#include <cmath>
#include <cstddef>
#include <cctype>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

struct CalculationResult
{
    std::string fuelName;
    double alpha = 0.;
    double beta = 0.;
    double gamma = 0.;
    double strainRate = 0.;          // 1/s
    double distance = 0.;            // cm
    double fuelVelocity = 0.;        // cm/s
    double oxidizerVelocity = 0.;    // cm/s
    double fuelTemperature = 0.;     // K
    double oxidizerTemperature = 0.; // K
    double fuelMassFraction = 0.;
    double fuelH2OMassFraction = 0.;
    double fuelO2MassFraction = 0.;
    double fuelN2MassFraction = 0.;
    double oxidizerH2OMassFraction = 0.;
    double oxidizerO2MassFraction = 0.;
    double oxidizerN2MassFraction = 0.;
};

std::string EscapeJsonString(const std::string& value)
{
    std::ostringstream escaped;

    for (const char character : value)
    {
        switch (character)
        {
            case '\"':
                escaped << "\\\"";
                break;
            case '\\':
                escaped << "\\\\";
                break;
            case '\b':
                escaped << "\\b";
                break;
            case '\f':
                escaped << "\\f";
                break;
            case '\n':
                escaped << "\\n";
                break;
            case '\r':
                escaped << "\\r";
                break;
            case '\t':
                escaped << "\\t";
                break;
            default:
                escaped << character;
                break;
        }
    }

    return escaped.str();
}

std::string EscapeCsvString(const std::string& value)
{
    bool mustQuote = false;
    std::ostringstream escaped;

    for (const char character : value)
    {
        if (character == '\"')
        {
            escaped << "\"\"";
            mustQuote = true;
        }
        else
        {
            escaped << character;
            if (character == ',' || character == '\n' || character == '\r')
            {
                mustQuote = true;
            }
        }
    }

    if (mustQuote)
    {
        return "\"" + escaped.str() + "\"";
    }

    return escaped.str();
}

std::string NumberToPathToken(const double value)
{
    std::ostringstream token;
    token << value;
    return token.str();
}

std::string NumberToText(const double value)
{
    std::ostringstream text;
    text << value;
    return text.str();
}

std::string StepDirectoryName(const int stepNumber,
                              const int maxStepNumber)
{
    const int width = std::max(2, static_cast<int>(
        std::to_string(maxStepNumber).size()));

    std::ostringstream directoryName;
    directoryName << "Step"
                  << std::setw(width)
                  << std::setfill('0')
                  << stepNumber;
    return directoryName.str();
}

std::filesystem::path BuildCaseDirectory(const CalculationResult& result)
{
    const std::string strainRateFolder =
        "a_" + NumberToPathToken(result.strainRate);
    const std::string caseFolder =
        "Alpha_" + NumberToPathToken(result.alpha) +
        "_Beta_" + NumberToPathToken(result.beta) +
        "_Gamma_" + NumberToPathToken(result.gamma);

    return std::filesystem::path(result.fuelName) /
           strainRateFolder /
           caseFolder;
}

std::filesystem::path BuildStrainRateDirectory(const CalculationResult& result)
{
    return std::filesystem::path(result.fuelName) /
           ("a_" + NumberToPathToken(result.strainRate));
}

std::string CaseDirectoryName(const CalculationResult& result)
{
    return "Alpha_" + NumberToPathToken(result.alpha) +
           "_Beta_" + NumberToPathToken(result.beta) +
           "_Gamma_" + NumberToPathToken(result.gamma);
}

std::string ReadTextFile(const std::filesystem::path& fileName)
{
    std::ifstream input(fileName);
    if (!input)
    {
        throw std::runtime_error("Unable to open template file: " +
                                 fileName.string());
    }

    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

void ReplaceAll(std::string& text,
                const std::string& placeholder,
                const std::string& value)
{
    std::size_t position = 0;
    while ((position = text.find(placeholder, position)) != std::string::npos)
    {
        text.replace(position, placeholder.size(), value);
        position += value.size();
    }
}

void WriteDefinitionJsonFile(const CalculationResult& result,
                             const std::string& jsonText)
{
    const std::filesystem::path caseDirectory = BuildCaseDirectory(result);
    std::filesystem::create_directories(caseDirectory);

    const std::filesystem::path definitionFile = caseDirectory / "definition.json";
    std::ofstream jsonFile(definitionFile);
    if (!jsonFile)
    {
        throw std::runtime_error("Unable to open JSON file for writing: " +
                                 definitionFile.string());
    }

    jsonFile << jsonText << '\n';
}

bool GetTemplateStepNumber(const std::filesystem::path& templateFile,
                           int& stepNumber)
{
    if (templateFile.extension() != ".template")
    {
        return false;
    }

    const std::string stem = templateFile.stem().string();
    const std::string prefix = "step";
    if (stem.size() <= prefix.size() ||
        stem.compare(0, prefix.size(), prefix) != 0)
    {
        return false;
    }

    const std::string stepText = stem.substr(prefix.size());
    for (const char character : stepText)
    {
        if (!std::isdigit(static_cast<unsigned char>(character)))
        {
            return false;
        }
    }

    stepNumber = std::stoi(stepText);
    return stepNumber > 0;
}

std::vector<std::pair<int, std::filesystem::path>> FindStepTemplates(
    const std::string& fuelName)
{
    const std::filesystem::path templatesDirectory =
        std::filesystem::path("templates") / fuelName;
    if (!std::filesystem::exists(templatesDirectory))
    {
        throw std::runtime_error("Unable to find template directory: " +
                                 templatesDirectory.string());
    }

    std::vector<std::pair<int, std::filesystem::path>> templates;
    for (const std::filesystem::directory_entry& entry :
         std::filesystem::directory_iterator(templatesDirectory))
    {
        if (!entry.is_regular_file())
        {
            continue;
        }

        int stepNumber = 0;
        if (GetTemplateStepNumber(entry.path(), stepNumber))
        {
            templates.emplace_back(stepNumber, entry.path());
        }
    }

    std::sort(templates.begin(), templates.end(),
              [](const auto& left, const auto& right)
              {
                  return left.first < right.first;
              });

    if (templates.empty())
    {
        throw std::runtime_error("No step*.template files found in: " +
                                 templatesDirectory.string());
    }

    return templates;
}

void ReplacePlaceholders(std::string& inputText,
                         const CalculationResult& result)
{
    const std::vector<std::pair<std::string, std::string>> replacements = {
        {"$VFUEL$", NumberToText(result.fuelVelocity)},
        {"$VOX$", NumberToText(result.oxidizerVelocity)},
        {"$TFUEL$", NumberToText(result.fuelTemperature)},
        {"$TOX$", NumberToText(result.oxidizerTemperature)},
        {"$ALPHA$", NumberToText(result.alpha)},
        {"$BETA$", NumberToText(result.beta)},
        {"$GAMMA$", NumberToText(result.gamma)},
        {"$STRAINRATE$", NumberToText(result.strainRate)},
        {"$Y1FUEL$", NumberToText(result.fuelMassFraction)},
        {"$Y1H2O$", NumberToText(result.fuelH2OMassFraction)},
        {"$Y1O2$", NumberToText(result.fuelO2MassFraction)},
        {"$Y1N2$", NumberToText(result.fuelN2MassFraction)},
        {"$Y2H2O$", NumberToText(result.oxidizerH2OMassFraction)},
        {"$Y2O2$", NumberToText(result.oxidizerO2MassFraction)},
        {"$YO2$", NumberToText(result.oxidizerO2MassFraction)},
        {"$Y2N2$", NumberToText(result.oxidizerN2MassFraction)}
    };

    for (const auto& replacement : replacements)
    {
        ReplaceAll(inputText, replacement.first, replacement.second);
    }
}

void WriteStepInputFile(const CalculationResult& result,
                        const int stepNumber,
                        const int maxStepNumber,
                        const std::filesystem::path& templateFile)
{
    std::string inputText = ReadTextFile(templateFile);
    ReplacePlaceholders(inputText, result);

    const std::filesystem::path stepDirectory =
        BuildCaseDirectory(result) / StepDirectoryName(stepNumber, maxStepNumber);
    std::filesystem::create_directories(stepDirectory);

    const std::filesystem::path inputFile = stepDirectory / "input.dic";
    std::ofstream output(inputFile);
    if (!output)
    {
        throw std::runtime_error("Unable to open step input file for writing: " +
                                 inputFile.string());
    }

    output << inputText;
}

void WriteRunScript(const CalculationResult& result,
                    const std::vector<std::pair<int, std::filesystem::path>>& templates)
{
    const int maxStepNumber = templates.back().first;
    const std::filesystem::path caseDirectory = BuildCaseDirectory(result);
    std::filesystem::create_directories(caseDirectory);

    const std::filesystem::path runFile = caseDirectory / "Run.sh";
    std::ofstream script(runFile);
    if (!script)
    {
        throw std::runtime_error("Unable to open run script for writing: " +
                                 runFile.string());
    }

    script << "#!/bin/bash\n\n"
           << "COMMAND=\"OpenSMOKEpp_CounterFlowFlame1D.sh\"\n"
           << "LOG_FILE=\"Run.log\"\n"
           << "STATUS_FILE=\"status.txt\"\n"
           << "EXIT_CODE_FILE=\"exit_code.txt\"\n"
           << "LAST_UPDATE_FILE=\"last_update.txt\"\n\n"
           << "MAX_TEMPERATURE_FILE=\"max_temperature_K.txt\"\n"
           << "STEP_STATUS_CSV=\"StepStatus.csv\"\n\n"
           << "MIN_VALID_MAX_TEMPERATURE_K=1000\n"
           << "LOW_TEMPERATURE_EXIT_CODE=10\n\n"
           << "timestamp() {\n"
           << "    date \"+%Y-%m-%d %H:%M:%S\"\n"
           << "}\n\n"
           << "mark_update() {\n"
           << "    timestamp > \"$LAST_UPDATE_FILE\"\n"
           << "}\n\n"
           << "log_message() {\n"
           << "    echo \"[$(timestamp)] $1\" | tee -a \"$LOG_FILE\"\n"
           << "    mark_update\n"
           << "}\n\n"
           << "append_step_status() {\n"
           << "    local step_directory=\"$1\"\n"
           << "    local status=\"$2\"\n"
           << "    local max_temperature=\"$3\"\n"
           << "    local exit_code=\"$4\"\n"
           << "    printf '\"%s\",\"%s\",\"%s\",\"%s\",\"%s\"\\n' \\\n"
           << "        \"$step_directory\" \"$status\" \"$max_temperature\" \"$exit_code\" \"$(timestamp)\" \\\n"
           << "        >> \"$STEP_STATUS_CSV\"\n"
           << "}\n\n"
           << "extract_max_temperature() {\n"
           << "    local step_directory=\"$1\"\n"
           << "    local xml_file=\"$step_directory/Output/Output.xml\"\n\n"
           << "    if [ ! -f \"$xml_file\" ]; then\n"
           << "        echo \"Output.xml not found: $xml_file\" >&2\n"
           << "        return 1\n"
           << "    fi\n\n"
           << "    awk '\n"
           << "        BEGIN {\n"
           << "            in_profiles = 0;\n"
           << "            in_size = 0;\n"
           << "            n = 0;\n"
           << "            m = 0;\n"
           << "            rows = 0;\n"
           << "            max_temperature = \"\";\n"
           << "        }\n"
           << "        /<profiles>/ {\n"
           << "            in_profiles = 1;\n"
           << "            next;\n"
           << "        }\n"
           << "        /<\\/profiles>/ {\n"
           << "            in_profiles = 0;\n"
           << "            next;\n"
           << "        }\n"
           << "        /<profiles-size>/ {\n"
           << "            in_size = 1;\n"
           << "            next;\n"
           << "        }\n"
           << "        /<\\/profiles-size>/ {\n"
           << "            in_size = 0;\n"
           << "            next;\n"
           << "        }\n"
           << "        in_size && NF >= 2 {\n"
           << "            n = $1 + 0;\n"
           << "            m = $2 + 0;\n"
           << "            next;\n"
           << "        }\n"
           << "        in_profiles && NF >= 2 {\n"
           << "            temperature = $2 + 0;\n"
           << "            if (max_temperature == \"\" || temperature > max_temperature) {\n"
           << "                max_temperature = temperature;\n"
           << "            }\n"
           << "            ++rows;\n"
           << "        }\n"
           << "        END {\n"
           << "            if (n <= 0 || m <= 0) {\n"
           << "                print \"profiles-size not found or invalid\" > \"/dev/stderr\";\n"
           << "                exit 2;\n"
           << "            }\n"
           << "            if (m < 2) {\n"
           << "                print \"profiles section has fewer than two columns\" > \"/dev/stderr\";\n"
           << "                exit 3;\n"
           << "            }\n"
           << "            if (rows <= 0 || max_temperature == \"\") {\n"
           << "                print \"profiles data not found\" > \"/dev/stderr\";\n"
           << "                exit 4;\n"
           << "            }\n"
           << "            if (rows != n) {\n"
           << "                printf \"warning: profiles-size reports %d rows, parsed %d rows\\n\", n, rows > \"/dev/stderr\";\n"
           << "            }\n"
           << "            printf \"%.10g\\n\", max_temperature;\n"
           << "        }\n"
           << "    ' \"$xml_file\"\n"
           << "}\n\n"
           << "run_step() {\n"
           << "    local step_directory=\"$1\"\n\n"
           << "    if [ ! -d \"$step_directory\" ]; then\n"
           << "        echo \"FAILED $step_directory\" > \"$STATUS_FILE\"\n"
           << "        echo \"1\" > \"$EXIT_CODE_FILE\"\n"
           << "        append_step_status \"$step_directory\" \"FAILED_MISSING_DIRECTORY\" \"\" \"1\"\n"
           << "        log_message \"Missing step directory: $step_directory\"\n"
           << "        exit 1\n"
           << "    fi\n\n"
           << "    echo \"RUNNING $step_directory\" > \"$STATUS_FILE\"\n"
           << "    append_step_status \"$step_directory\" \"RUNNING\" \"\" \"\"\n"
           << "    log_message \"Starting $step_directory\"\n\n"
           << "    (\n"
           << "        cd \"$step_directory\" || exit 1\n"
           << "        \"$COMMAND\" > log.out 2> log.err\n"
           << "    )\n"
           << "    local exit_code=$?\n\n"
           << "    if [ \"$exit_code\" -ne 0 ]; then\n"
           << "        echo \"FAILED $step_directory\" > \"$STATUS_FILE\"\n"
           << "        echo \"$exit_code\" > \"$EXIT_CODE_FILE\"\n"
           << "        append_step_status \"$step_directory\" \"FAILED_SOLVER\" \"\" \"$exit_code\"\n"
           << "        log_message \"Failed $step_directory with exit code $exit_code\"\n"
           << "        exit \"$exit_code\"\n"
           << "    fi\n\n"
           << "    local max_temperature\n"
           << "    max_temperature=$(extract_max_temperature \"$step_directory\" 2> \"$step_directory/max_temperature.err\")\n"
           << "    exit_code=$?\n"
           << "    if [ \"$exit_code\" -ne 0 ]; then\n"
           << "        echo \"FAILED $step_directory OUTPUT_XML\" > \"$STATUS_FILE\"\n"
           << "        echo \"$exit_code\" > \"$EXIT_CODE_FILE\"\n"
           << "        append_step_status \"$step_directory\" \"FAILED_OUTPUT_XML\" \"\" \"$exit_code\"\n"
           << "        log_message \"Failed to extract maximum temperature from $step_directory/Output/Output.xml\"\n"
           << "        exit \"$exit_code\"\n"
           << "    fi\n\n"
           << "    echo \"$max_temperature\" > \"$MAX_TEMPERATURE_FILE\"\n"
           << "    echo \"$max_temperature\" > \"$step_directory/max_temperature_K.txt\"\n"
           << "    if awk -v temperature=\"$max_temperature\" \\\n"
           << "           -v minimum=\"$MIN_VALID_MAX_TEMPERATURE_K\" \\\n"
           << "           'BEGIN { exit (temperature < minimum) ? 0 : 1 }'; then\n"
           << "        echo \"FAILED $step_directory LOW_TEMPERATURE\" > \"$STATUS_FILE\"\n"
           << "        echo \"$LOW_TEMPERATURE_EXIT_CODE\" > \"$EXIT_CODE_FILE\"\n"
           << "        append_step_status \"$step_directory\" \"FAILED_LOW_TEMPERATURE\" \"$max_temperature\" \"$LOW_TEMPERATURE_EXIT_CODE\"\n"
           << "        log_message \"Failed $step_directory: max_temperature_K=$max_temperature below threshold $MIN_VALID_MAX_TEMPERATURE_K K\"\n"
           << "        exit \"$LOW_TEMPERATURE_EXIT_CODE\"\n"
           << "    fi\n\n"
           << "    append_step_status \"$step_directory\" \"COMPLETED\" \"$max_temperature\" \"0\"\n"
           << "    log_message \"Completed $step_directory max_temperature_K=$max_temperature\"\n"
           << "}\n\n"
           << ": > \"$LOG_FILE\"\n"
           << ": > \"$EXIT_CODE_FILE\"\n"
           << ": > \"$MAX_TEMPERATURE_FILE\"\n"
           << "echo \"step,status,max_temperature_K,exit_code,last_update\" > \"$STEP_STATUS_CSV\"\n"
           << "echo \"RUNNING\" > \"$STATUS_FILE\"\n"
           << "mark_update\n"
           << "log_message \"Started case $(basename \"$PWD\")\"\n\n";

    for (const auto& stepTemplate : templates)
    {
        script << "run_step \""
               << StepDirectoryName(stepTemplate.first, maxStepNumber)
               << "\"\n";
    }

    script << "\n"
           << "echo \"COMPLETED\" > \"$STATUS_FILE\"\n"
           << "echo \"0\" > \"$EXIT_CODE_FILE\"\n"
           << "log_message \"Completed all steps\"\n";

    script.close();
    std::filesystem::permissions(
        runFile,
        std::filesystem::perms::owner_exec |
            std::filesystem::perms::group_exec |
            std::filesystem::perms::others_exec,
        std::filesystem::perm_options::add);
}

void WriteStepInputFiles(const CalculationResult& result)
{
    const std::vector<std::pair<int, std::filesystem::path>> templates =
        FindStepTemplates(result.fuelName);
    const int maxStepNumber = templates.back().first;

    for (const auto& stepTemplate : templates)
    {
        WriteStepInputFile(result,
                           stepTemplate.first,
                           maxStepNumber,
                           stepTemplate.second);
    }

    WriteRunScript(result, templates);
}

void WriteRunAllScript(const std::vector<CalculationResult>& results)
{
    if (results.empty())
    {
        return;
    }

    const std::filesystem::path strainRateDirectory =
        BuildStrainRateDirectory(results.front());
    std::filesystem::create_directories(strainRateDirectory);

    const std::filesystem::path runAllFile = strainRateDirectory / "RunAll.sh";
    std::ofstream script(runAllFile);
    if (!script)
    {
        throw std::runtime_error("Unable to open campaign run script for writing: " +
                                 runAllFile.string());
    }

    script << "#!/bin/bash\n\n"
           << "NP=\"${1:-1}\"\n"
           << "CAMPAIGN_LOG=\"Campaign.log\"\n"
           << "STATUS_CSV=\"CampaignStatus.csv\"\n\n"
           << "if ! [[ \"$NP\" =~ ^[0-9]+$ ]] || [ \"$NP\" -lt 1 ]; then\n"
           << "    echo \"Usage: ./RunAll.sh <number-of-parallel-cases>\"\n"
           << "    exit 1\n"
           << "fi\n\n"
           << "CASES=(\n";

    for (const CalculationResult& result : results)
    {
        script << "    \"" << CaseDirectoryName(result) << "\"\n";
    }

    script << ")\n\n"
           << "timestamp() {\n"
           << "    date \"+%Y-%m-%d %H:%M:%S\"\n"
           << "}\n\n"
           << "active_jobs() {\n"
           << "    jobs -rp | wc -l | tr -d ' '\n"
           << "}\n\n"
           << "log_message() {\n"
           << "    echo \"[$(timestamp)] $1\" | tee -a \"$CAMPAIGN_LOG\"\n"
           << "}\n\n"
           << "read_case_file() {\n"
           << "    local file_name=\"$1\"\n"
           << "    if [ -f \"$file_name\" ]; then\n"
           << "        tr -d '\\n' < \"$file_name\"\n"
           << "    fi\n"
           << "}\n\n"
           << "write_status() {\n"
           << "    echo \"case,status,last_update,pid,exit_code,max_temperature_K\" > \"$STATUS_CSV\"\n"
           << "    local status_case_directory\n"
           << "    for status_case_directory in \"${CASES[@]}\"; do\n"
           << "        local status=\"PENDING\"\n"
           << "        local last_update=\"\"\n"
           << "        local pid=\"\"\n"
           << "        local exit_code=\"\"\n\n"
           << "        local max_temperature=\"\"\n\n"
           << "        if [ -f \"$status_case_directory/status.txt\" ]; then\n"
           << "            status=$(read_case_file \"$status_case_directory/status.txt\")\n"
           << "        fi\n"
           << "        if [ -f \"$status_case_directory/last_update.txt\" ]; then\n"
           << "            last_update=$(read_case_file \"$status_case_directory/last_update.txt\")\n"
           << "        fi\n"
           << "        if [ -f \"$status_case_directory/pid.txt\" ]; then\n"
           << "            pid=$(read_case_file \"$status_case_directory/pid.txt\")\n"
           << "        fi\n"
           << "        if [ -f \"$status_case_directory/exit_code.txt\" ]; then\n"
           << "            exit_code=$(read_case_file \"$status_case_directory/exit_code.txt\")\n"
           << "        fi\n\n"
           << "        if [ -f \"$status_case_directory/max_temperature_K.txt\" ]; then\n"
           << "            max_temperature=$(read_case_file \"$status_case_directory/max_temperature_K.txt\")\n"
           << "        fi\n\n"
           << "        printf '\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\"\\n' \\\n"
           << "            \"$status_case_directory\" \"$status\" \"$last_update\" \"$pid\" \"$exit_code\" \"$max_temperature\" \\\n"
           << "            >> \"$STATUS_CSV\"\n"
           << "    done\n"
           << "}\n\n"
           << "run_case() {\n"
           << "    local case_directory=\"$1\"\n"
           << "    echo \"RUNNING\" > \"$case_directory/status.txt\"\n"
           << "    timestamp > \"$case_directory/last_update.txt\"\n"
           << "    (\n"
           << "        cd \"$case_directory\" || exit 0\n"
           << "        ./Run.sh > Run.stdout 2> Run.stderr\n"
           << "        run_exit_code=$?\n"
           << "        if [ ! -s exit_code.txt ]; then\n"
           << "            echo \"$run_exit_code\" > exit_code.txt\n"
           << "        fi\n"
           << "        timestamp > last_update.txt\n"
           << "        exit 0\n"
           << "    ) &\n\n"
           << "    local pid=$!\n"
           << "    echo \"$pid\" > \"$case_directory/pid.txt\"\n"
           << "    log_message \"Started $case_directory with PID $pid\"\n"
           << "}\n\n"
           << ": > \"$CAMPAIGN_LOG\"\n"
           << "log_message \"Campaign started with NP=$NP and NC=${#CASES[@]}\"\n\n"
           << "for case_directory in \"${CASES[@]}\"; do\n"
           << "    if [ ! -f \"$case_directory/Run.sh\" ]; then\n"
           << "        log_message \"Run.sh was not found in $case_directory\"\n"
           << "        exit 1\n"
           << "    fi\n\n"
           << "    if [ ! -x \"$case_directory/Run.sh\" ]; then\n"
           << "        chmod +x \"$case_directory/Run.sh\" || {\n"
           << "            log_message \"Unable to make Run.sh executable in $case_directory\"\n"
           << "            exit 1\n"
           << "        }\n"
           << "    fi\n\n"
           << "    echo \"PENDING\" > \"$case_directory/status.txt\"\n"
           << "    : > \"$case_directory/pid.txt\"\n"
           << "    : > \"$case_directory/exit_code.txt\"\n"
           << "    : > \"$case_directory/max_temperature_K.txt\"\n"
           << "    timestamp > \"$case_directory/last_update.txt\"\n"
           << "done\n\n"
           << "write_status\n\n"
           << "for case_directory in \"${CASES[@]}\"; do\n"
           << "    while [ \"$(active_jobs)\" -ge \"$NP\" ]; do\n"
           << "        write_status\n"
           << "        sleep 5\n"
           << "    done\n\n"
           << "    run_case \"$case_directory\"\n"
           << "    write_status\n"
           << "done\n\n"
           << "while [ \"$(active_jobs)\" -gt 0 ]; do\n"
           << "    write_status\n"
           << "    sleep 5\n"
           << "done\n\n"
           << "wait\n"
           << "write_status\n\n"
           << "failed=0\n"
           << "for final_case_directory in \"${CASES[@]}\"; do\n"
           << "    exit_code=$(read_case_file \"$final_case_directory/exit_code.txt\")\n"
           << "    if [ \"$exit_code\" != \"0\" ]; then\n"
           << "        failed=1\n"
           << "        log_message \"Failed case: $final_case_directory exit_code=$exit_code\"\n"
           << "    fi\n"
           << "done\n\n"
           << "if [ \"$failed\" -ne 0 ]; then\n"
           << "    log_message \"Campaign completed; some cases failed, but all scheduled cases were processed\"\n"
           << "    exit 0\n"
           << "fi\n\n"
           << "log_message \"Campaign completed successfully\"\n"
           << "exit 0\n";

    script.close();
    std::filesystem::permissions(
        runAllFile,
        std::filesystem::perms::owner_exec |
            std::filesystem::perms::group_exec |
            std::filesystem::perms::others_exec,
        std::filesystem::perm_options::add);
}

std::string Calculate(const std::string& namef,
                      const double MWf,
                      const double alpha,
                      const double beta,
                      const double gamma,
                      const double a,
                      const double L,
                      CalculationResult* result = nullptr)
{
    // Counterflow burner separation. The oxidizer-side velocity is imposed
    // from the strain rate by v2 = a*L/4.

    // Temperatures
    const double T1 = 293.;  // K
    const double T2 = 293.;  // K

    // Molecular weights [kg/kmol]. Oxidizer and air are both treated as
    // regular air with 23.2% O2 and 76.8% N2 by mass.
    const double MWs = 18.;    // steam/H2O
    const double MWo = 28.84;  // pure oxidizer stream, assumed air
    const double MWa = 28.84;  // additional air

    // Use one unit of pure fuel as reference. alpha governs total steam
    // addition, beta governs additional air relative to steam, and gamma
    // splits those additions between fuel side (gamma) and oxidizer side
    // (1-gamma).
    const double m1f = 1.;
    const double m1s = alpha * gamma * m1f;
    const double m2s = alpha * (1. - gamma) * m1f;
    const double m1a = alpha * beta * gamma * m1f;
    const double m2a = alpha * beta * (1. - gamma) * m1f;

    // Fuel-side mass fractions and mixture molecular weight.
    const double m1 = m1f + m1s + m1a;
    const double Y1f = m1f / m1;
    const double Y1s = m1s / m1;
    const double Y1a = m1a / m1;
    const double MW1 = 1. / (Y1f / MWf + Y1s / MWs + Y1a / MWa);

    const double v2 = a * L / 4.;  // cm/s
    double Y2_H2O = 0.;
    double Y2_O2 = 0.;
    double Y2_N2 = 0.;

    // R = v1/v2. Since the oxidizer stream composition depends on R, solve it
    // by fixed-point iterations. Ten iterations reproduce the original model.
    double R = std::sqrt( (MWo/T1) / (MWf/T2) );
    for (int i = 0; i < 10; ++i)
    {
        const double N1 = 1. + alpha * gamma + alpha * beta * gamma;
        const double N2 = alpha * (1. - gamma) * (1. + beta);
        const double delta = N1 * R - N2;
        const double m2o = delta;
        const double m2 = m2o + m2s + m2a;

        const double Y2o = m2o / m2;
        const double Y2s = m2s / m2;
        const double Y2a = m2a / m2;

        const double MW2 = 1. / (Y2o / MWo + Y2s / MWs + Y2a / MWa);

        R = std::sqrt( (MW2/T2) / (MW1/T1) );

        // Oxidizer properties
        Y2_H2O = Y2s;
        Y2_O2 = (Y2o + Y2a) * 0.232;
        Y2_N2 = (Y2o + Y2a) * 0.768;
    }

    // Fuel properties
    const double v1 = v2 * R;
    const double Y1_F = Y1f;
    const double Y1_H2O = Y1s;
    const double Y1_O2 = Y1a * 0.232;
    const double Y1_N2 = Y1a * 0.768;

    CalculationResult localResult;
    localResult.fuelName = namef;
    localResult.alpha = alpha;
    localResult.beta = beta;
    localResult.gamma = gamma;
    localResult.strainRate = a;
    localResult.distance = L;
    localResult.fuelVelocity = v1;
    localResult.oxidizerVelocity = v2;
    localResult.fuelTemperature = T1;
    localResult.oxidizerTemperature = T2;
    localResult.fuelMassFraction = Y1_F;
    localResult.fuelH2OMassFraction = Y1_H2O;
    localResult.fuelO2MassFraction = Y1_O2;
    localResult.fuelN2MassFraction = Y1_N2;
    localResult.oxidizerH2OMassFraction = Y2_H2O;
    localResult.oxidizerO2MassFraction = Y2_O2;
    localResult.oxidizerN2MassFraction = Y2_N2;

    if (result != nullptr)
    {
        *result = localResult;
    }

    std::ostringstream json;
    json << "{\n"
         << "  \"fuel_name\": \"" << EscapeJsonString(localResult.fuelName) << "\",\n"
         << "  \"parameters\": {\n"
         << "    \"alpha\": " << localResult.alpha << ",\n"
         << "    \"beta\": " << localResult.beta << ",\n"
         << "    \"gamma\": " << localResult.gamma << "\n"
         << "  },\n"
         << "  \"strain_rate\": { \"value\": " << localResult.strainRate << ", \"unit\": \"1/s\" },\n"
         << "  \"distance\": { \"value\": " << localResult.distance << ", \"unit\": \"cm\" },\n"
         << "  \"fuel\": {\n"
         << "    \"velocity\": { \"value\": " << localResult.fuelVelocity << ", \"unit\": \"cm/s\" },\n"
         << "    \"temperature\": { \"value\": " << localResult.fuelTemperature << ", \"unit\": \"K\" },\n"
         << "    \"mass_fractions\": {\n"
         << "      \"" << EscapeJsonString(localResult.fuelName) << "\": " << localResult.fuelMassFraction << ",\n"
         << "      \"H2O\": " << localResult.fuelH2OMassFraction << ",\n"
         << "      \"O2\": " << localResult.fuelO2MassFraction << ",\n"
         << "      \"N2\": " << localResult.fuelN2MassFraction << "\n"
         << "    }\n"
         << "  },\n"
         << "  \"oxidizer\": {\n"
         << "    \"velocity\": { \"value\": " << localResult.oxidizerVelocity << ", \"unit\": \"cm/s\" },\n"
         << "    \"temperature\": { \"value\": " << localResult.oxidizerTemperature << ", \"unit\": \"K\" },\n"
         << "    \"mass_fractions\": {\n"
         << "      \"H2O\": " << localResult.oxidizerH2OMassFraction << ",\n"
         << "      \"O2\": " << localResult.oxidizerO2MassFraction << ",\n"
         << "      \"N2\": " << localResult.oxidizerN2MassFraction << "\n"
         << "    }\n"
         << "  }\n"
         << "}";

    return json.str();
}

std::string Trim(const std::string& text)
{
    std::size_t begin = 0;
    while (begin < text.size() &&
           std::isspace(static_cast<unsigned char>(text[begin])))
    {
        ++begin;
    }

    std::size_t end = text.size();
    while (end > begin &&
           std::isspace(static_cast<unsigned char>(text[end - 1])))
    {
        --end;
    }

    return text.substr(begin, end - begin);
}

std::vector<double> ParseDoubleList(const std::string& text)
{
    std::vector<double> values;
    std::size_t begin = 0;

    while (begin <= text.size())
    {
        const std::size_t comma = text.find(',', begin);
        const std::size_t end = (comma == std::string::npos) ? text.size() : comma;
        const std::string token = Trim(text.substr(begin, end - begin));

        if (token.empty())
        {
            throw std::invalid_argument("Empty value in numerical list: " + text);
        }

        std::size_t parsedCharacters = 0;
        double value = 0.;
        try
        {
            value = std::stod(token, &parsedCharacters);
        }
        catch (const std::exception&)
        {
            throw std::invalid_argument("Invalid numerical value: " + token);
        }

        if (parsedCharacters != token.size())
        {
            throw std::invalid_argument("Invalid numerical value: " + token);
        }

        values.push_back(value);

        if (comma == std::string::npos)
        {
            break;
        }
        begin = comma + 1;
    }

    if (values.empty())
    {
        throw std::invalid_argument("At least one numerical value is required.");
    }

    return values;
}

double ParseDoubleValue(const std::string& text,
                        const std::string& optionName)
{
    const std::string token = Trim(text);
    if (token.empty())
    {
        throw std::invalid_argument("Missing numerical value for option: " +
                                    optionName);
    }

    std::size_t parsedCharacters = 0;
    double value = 0.;
    try
    {
        value = std::stod(token, &parsedCharacters);
    }
    catch (const std::exception&)
    {
        throw std::invalid_argument("Invalid numerical value for " +
                                    optionName + ": " + token);
    }

    if (parsedCharacters != token.size())
    {
        throw std::invalid_argument("Invalid numerical value for " +
                                    optionName + ": " + token);
    }

    return value;
}

void WriteCsvFile(const std::string& fileName,
                  const std::vector<CalculationResult>& results)
{
    std::ofstream csv(fileName);
    if (!csv)
    {
        throw std::runtime_error("Unable to open CSV file for writing: " + fileName);
    }

    csv << "fuel_name,"
        << "alpha,beta,gamma,"
        << "strain_rate_1_per_s,"
        << "distance_cm,"
        << "fuel_velocity_cm_per_s,"
        << "oxidizer_velocity_cm_per_s,"
        << "fuel_temperature_K,"
        << "oxidizer_temperature_K,"
        << "fuel_Y_fuel,"
        << "fuel_Y_H2O,"
        << "fuel_Y_O2,"
        << "fuel_Y_N2,"
        << "oxidizer_Y_H2O,"
        << "oxidizer_Y_O2,"
        << "oxidizer_Y_N2\n";

    for (const CalculationResult& result : results)
    {
        csv << EscapeCsvString(result.fuelName) << ','
            << result.alpha << ','
            << result.beta << ','
            << result.gamma << ','
            << result.strainRate << ','
            << result.distance << ','
            << result.fuelVelocity << ','
            << result.oxidizerVelocity << ','
            << result.fuelTemperature << ','
            << result.oxidizerTemperature << ','
            << result.fuelMassFraction << ','
            << result.fuelH2OMassFraction << ','
            << result.fuelO2MassFraction << ','
            << result.fuelN2MassFraction << ','
            << result.oxidizerH2OMassFraction << ','
            << result.oxidizerO2MassFraction << ','
            << result.oxidizerN2MassFraction << '\n';
    }
}

void PrintUsage(const char* programName)
{
    std::cerr << "Usage: " << programName
              << " --fuel <name> --fuel-mw <value> --strain-rate <value> --distance <value>\n"
              << "       --alpha <values> --beta <values> --gamma <values> [--csv <file>]\n"
              << "\n"
              << "Defaults: --fuel C7H8 --fuel-mw 92 --strain-rate 25 --distance 1.5\n"
              << "\n"
              << "Each list is comma-separated, for example:\n"
              << "  " << programName
              << " --fuel CH4 --fuel-mw 16 --strain-rate 100 --distance 1.5"
              << " --alpha 0.2,0.5 --beta 0.1 --gamma 0.0,0.5,1.0"
              << " --csv CFDF_results.csv\n"
              << "The form --alpha=0.2,0.5 is also accepted.\n";
}

int main(const int argc, char* argv[])
{
    std::vector<double> alphas = {0.5};
    std::vector<double> betas = {0.5};
    std::vector<double> gammas = {0.5};
    std::string csvFileName = "CFDF_results.csv";
    std::string fuelName = "C7H8";
    double fuelMolecularWeight = 92.;  // kg/kmol
    double strainRate = 25.;           // 1/s
    double distance = 1.5;             // cm

    try
    {
        for (int i = 1; i < argc; ++i)
        {
            const std::string argument = argv[i];
            if (argument == "--help" || argument == "-h")
            {
                PrintUsage(argv[0]);
                return 0;
            }

            std::string option;
            std::string values;
            const std::size_t separator = argument.find('=');
            if (separator != std::string::npos)
            {
                option = argument.substr(0, separator);
                values = argument.substr(separator + 1);
            }
            else
            {
                option = argument;
                if (i + 1 >= argc)
                {
                    throw std::invalid_argument("Missing value after option: " + option);
                }
                values = argv[++i];
            }

            if (option == "--alpha")
            {
                alphas = ParseDoubleList(values);
            }
            else if (option == "--beta")
            {
                betas = ParseDoubleList(values);
            }
            else if (option == "--gamma")
            {
                gammas = ParseDoubleList(values);
            }
            else if (option == "--csv")
            {
                csvFileName = values;
            }
            else if (option == "--fuel" || option == "--fuel-name")
            {
                fuelName = Trim(values);
                if (fuelName.empty())
                {
                    throw std::invalid_argument("Fuel name cannot be empty.");
                }
            }
            else if (option == "--fuel-mw" ||
                     option == "--molecular-weight" ||
                     option == "--mw")
            {
                fuelMolecularWeight = ParseDoubleValue(values, option);
                if (fuelMolecularWeight <= 0.)
                {
                    throw std::invalid_argument(
                        "Fuel molecular weight must be positive.");
                }
            }
            else if (option == "--strain-rate" || option == "--a")
            {
                strainRate = ParseDoubleValue(values, option);
                if (strainRate <= 0.)
                {
                    throw std::invalid_argument("Strain rate must be positive.");
                }
            }
            else if (option == "--distance" || option == "--L")
            {
                distance = ParseDoubleValue(values, option);
                if (distance <= 0.)
                {
                    throw std::invalid_argument("Distance must be positive.");
                }
            }
            else
            {
                throw std::invalid_argument("Unknown option: " + option);
            }
        }
    }
    catch (const std::exception& error)
    {
        std::cerr << "Error: " << error.what() << "\n\n";
        PrintUsage(argv[0]);
        return 1;
    }

    std::vector<CalculationResult> results;
    std::vector<std::string> jsonTexts;
    results.reserve(alphas.size() * betas.size() * gammas.size());
    jsonTexts.reserve(alphas.size() * betas.size() * gammas.size());

    try
    {
        for (const double alpha : alphas)
        {
            for (const double beta : betas)
            {
                for (const double gamma : gammas)
                {
                    CalculationResult result;
                    const std::string jsonText = Calculate(fuelName,
                                                           fuelMolecularWeight,
                                                           alpha,
                                                           beta,
                                                           gamma,
                                                           strainRate,
                                                           distance,
                                                           &result);
                    results.push_back(result);
                    jsonTexts.push_back(jsonText);
                }
            }
        }

        for (std::size_t i = 0; i < results.size(); ++i)
        {
            WriteDefinitionJsonFile(results[i], jsonTexts[i]);
            WriteStepInputFiles(results[i]);
        }

        WriteRunAllScript(results);
        WriteCsvFile(csvFileName, results);
    }
    catch (const std::exception& error)
    {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    std::cout << "[\n";
    for (std::size_t i = 0; i < jsonTexts.size(); ++i)
    {
        if (i > 0)
        {
            std::cout << ",\n";
        }

        std::cout << jsonTexts[i];
    }
    std::cout << "\n]\n";

    return 0;
}
