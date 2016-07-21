#include <Python.h>
#include <stdbool.h>

// Use for returning errors
#define err_size 500
// Use as a special pointer value
#define done_parsing  (void *)1
// Check if a bit is set
#define CHECK_BIT(var,pos) ((var) & (1<<(pos)))

// Check if py3
#if PY_MAJOR_VERSION >= 3
#define IS_PY3K
#endif

// Our whitepspace chars
char whitespace[4] = " \n\t\v";
bool verbose = false;

// A parser struct to keep track of state
typedef struct {
    char * source;
    char * full_data;
    char * token;
    long index;
    long length;
    char last_delineator;
} parser_data;

// Initialize the parser
parser_data parser = {NULL, NULL, done_parsing, 0, 0, ' '};

void reset_parser(parser_data * parser){

    if (parser->source != NULL){
        free(parser->full_data);
        parser->source = NULL;
    }

    parser->full_data = NULL;
    if (parser->token != done_parsing){
        free(parser->token);
    }
    parser->token = NULL;
    parser->index = 0;
    parser->length = 0;
    parser->last_delineator = ' ';
}

/* Return the index of the first match of needle in haystack, or -1 */
long get_index(char * haystack, char * needle, long start_pos){

    haystack += sizeof(char) * start_pos;
    char * start = strstr(haystack, needle);

    // Return the end if string not found
    if (!start){
        return -1;
    }

    // Calculate the length into start is the new word
    long diff = start - haystack;
    return diff;
}

/* Use to look for common unset bits between strings.
void get_common_bits(void){
    char one[5] = "data_";
    char two[5] = "save_";
    char three[5] = "loop_";
    char four[5] = "stop_";
    char five[5] = "globa";
    char comb[5];

    int x;
    for (x=0; x< 5; x++){
        comb[x] = (char)(one[x] | two[x] | three[x] | four[x] | five[x]);
    }

    printf("Comb: \n");
    for (x=0; x< 5; x++){
        int y;
        for (y=0; y<7; y++){
            if (CHECK_BIT(comb[x], y)){
                printf("%d.%d: 1\n", x, y);
            } else {
                printf("%d.%d: 0\n", x, y);
            }
        }
    }
    return;
}*/


void get_file(char *fname, parser_data * parser){

    reset_parser(parser);

    // Open the file
    FILE *f = fopen(fname, "rb");
    if (!f){
        PyErr_SetString(PyExc_IOError, "Could not open file.");
        return;
    }

    // Determine how long it is
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);

    // Allocate space for the file in RAM and load the file
    char *string = malloc(fsize + 1);
    if (fread(string, fsize, 1, f) != 1){
        PyErr_SetString(PyExc_IOError, "Short read of file.");
        return;
    }

    fclose(f);
    // Zero terminate
    string[fsize] = 0;

    parser->full_data = string;
    parser->length = fsize;
    parser->source = fname;
    parser->index = 0;
    parser->last_delineator = ' ';
}

/* Determines if a character is whitespace */
bool is_whitespace(char test){
    int x;
    for (x=0; x<sizeof(whitespace); x++){
        if (test == whitespace[x]){
            return true;
        }
    }
    return false;
}

/* Returns the index of the next whitespace in the string. */
long get_next_whitespace(char * string, long start_pos){

    long pos = start_pos;
    while (string[pos] != '\0'){
        if (is_whitespace(string[pos])){
            return pos;
        }
        pos++;
    }
    return pos;
}

/* Scan the index to the next non-whitespace char */
void pass_whitespace(parser_data * parser){
    while ((parser->index < parser->length) &&
            (is_whitespace(parser->full_data[parser->index]))){
        parser->index++;
    }
}

bool check_multiline(parser_data * parser, long length){
    long x;
    for (x=parser->index; x <= parser->index+length; x++){
        if (parser->full_data[x] == '\n'){
            return true;
        }
    }
    return false;

}

/* Returns a new token char * */
char * update_token(parser_data * parser, long length){

    if (parser->token != done_parsing){
        free(parser->token);
    }
    parser->token = malloc(length+1);
    //printf("index %ld par_len %ld my_len %ld\n", parser->index, parser->length, length);
    memcpy(parser->token, &parser->full_data[parser->index], length);
    parser->token[length] = '\0';

    // Figure out what to set the last delineator as
    if (parser->index == 0){
        parser->last_delineator = ' ';
    } else {
        char ld = parser->full_data[parser->index-1];
        if ((ld == '\n') && (parser->index > 2) && (parser->full_data[parser->index-2] == ';')){
            parser->last_delineator = ';';
        } else if ((ld == '"') || (ld == '\'')){
            parser->last_delineator = ld;
        } else {
            parser->last_delineator = ' ';
        }
    }

    parser->index += length + 1;
    return parser->token;
}


// Get the current line number
long get_line_number(parser_data * parser){
    long num_lines = 0;
    long x;
    for (x = 0; x < parser->index; x++){
        if (parser->full_data[x] == '\n'){
            num_lines++;
        }
    }
    return num_lines + 1;
}

char * get_token(parser_data * parser){

    // Reset the delineator
    parser->last_delineator = '?';

    // Set up a tmp str pointer to use for searches
    char * search;
    // And an error char array
    char err[err_size] = "Unknown error.";

    // Nothing left
    if (parser->token == done_parsing){
        return parser->token;
    }

    // Skip whitespace
    pass_whitespace(parser);

    // Stop if we are at the end
    if (parser->index >= parser->length){
        free(parser->token);
        parser->token = done_parsing;
        return parser->token;
    }

    // See if this is a comment - if so skip it
    if (parser->full_data[parser->index] == '#'){
        search = "\n";
        long length = get_index(parser->full_data, search, parser->index);

        // Handle the edge case where this is the last line of the file and there is no newline
        if (length == -1){
            free(parser->token);
            parser->token = done_parsing;
            return parser->token;
        }

        // Skip to the next non-comment
        parser->index += length;
        return get_token(parser);
    }

    // See if this is a multiline comment
    if ((parser->length - parser->index > 1) && (parser->full_data[parser->index] == ';') && (parser->full_data[parser->index+1] == '\n')){
        search = "\n;";
        long length = get_index(parser->full_data, search, parser->index);

        // Handle the edge case where this is the last line of the file and there is no newline
        if (length == -1){
            snprintf(err, sizeof(err), "Invalid file. Semicolon-delineated value was not terminated. Error on line: %ld", get_line_number(parser));
            PyErr_SetString(PyExc_ValueError, err);
            free(parser->token);
            parser->token = NULL;
            return parser->token;
        }

        parser->index += 2;
        return update_token(parser, length-1);
    }

    // Handle values quoted with '
    if (parser->full_data[parser->index] == '\''){
        search = "'";
        long end_quote = get_index(parser->full_data, search, parser->index + 1);

        // Handle the case where there is no terminating quote in the file
        if (end_quote == -1){
            snprintf(err, sizeof(err), "Invalid file. Single quoted value was not terminated. Error on line: %ld", get_line_number(parser));
            PyErr_SetString(PyExc_ValueError, err);
            free(parser->token);
            parser->token = NULL;
            return parser->token;
        }

        // Make sure we don't stop for quotes that are not followed by whitespace
        while ((parser->index+end_quote+2 < parser->length) && (!is_whitespace(parser->full_data[parser->index+end_quote+2]))){
            long next_index = get_index(parser->full_data, search, parser->index+end_quote+2);
            if (next_index == -1){
                PyErr_SetString(PyExc_ValueError, "Invalid file. Single quoted value was never terminated at end of file.");
                free(parser->token);
                parser->token = NULL;
                return parser->token;
            }
            end_quote += next_index + 1;
        }

        // See if the quote has a newline
        if (check_multiline(parser, end_quote)){
            snprintf(err, sizeof(err), "Invalid file. Single quoted value was not terminated on the same line it began. Error on line: %ld", get_line_number(parser));
            PyErr_SetString(PyExc_ValueError, err);
            free(parser->token);
            parser->token = NULL;
            return parser->token;
        }

        // Move the index 1 to skip the '
        parser->index++;
        return update_token(parser, end_quote);
    }

    // Handle values quoted with "
    if (parser->full_data[parser->index] == '\"'){
        search = "\"";
        long end_quote = get_index(parser->full_data, search, parser->index + 1);

        // Handle the case where there is no terminating quote in the file
        if (end_quote == -1){
            snprintf(err, sizeof(err), "Invalid file. Double quoted value was not terminated. Error on line: %ld", get_line_number(parser));
            PyErr_SetString(PyExc_ValueError, err);
            free(parser->token);
            parser->token = NULL;
            return parser->token;
        }

        // Make sure we don't stop for quotes that are not followed by whitespace
        while ((parser->index+end_quote+2 < parser->length) && (!is_whitespace(parser->full_data[parser->index+end_quote+2]))){
            long next_index = get_index(parser->full_data, search, parser->index+end_quote+2);
            if (next_index == -1){
                PyErr_SetString(PyExc_ValueError, "Invalid file. Double quoted value was never terminated at end of file.");
                free(parser->token);
                parser->token = NULL;
                return parser->token;
            }
            end_quote += next_index + 1;
        }

        // See if the quote has a newline
        if (check_multiline(parser, end_quote)){
            snprintf(err, sizeof(err), "Invalid file. Double quoted value was not terminated on the same line it began. Error on line: %ld", get_line_number(parser));
            PyErr_SetString(PyExc_ValueError, err);
            free(parser->token);
            parser->token = NULL;
            return parser->token;
        }

        // Move the index 1 to skip the "
        parser->index++;
        return update_token(parser, end_quote);
    }

    // Nothing special. Just get the token
    long end_pos = get_next_whitespace(parser->full_data, parser->index);
    return update_token(parser, end_pos - parser->index);
}

// Implements startswith
bool starts_with(const char *a, const char *b)
{
   if(strncmp(a, b, strlen(b)) == 0) return true;
   return false;
}

/*
    Automatically quotes the value in the appropriate way. Don't
    quote values you send to this method or they will show up in
    another set of quotes as part of the actual data. E.g.:

    clean_value('"e. coli"') returns '\'"e. coli"\''

    while

    clean_value("e. coli") returns "'e. coli'"
*/
static PyObject * clean_string(PyObject *self, PyObject *args){
    char * str;

    // Get the string to clean
    if (!PyArg_ParseTuple(args, "s", &str))
        return NULL;

    // Figure out how long the string is
    long len = strlen(str);

    // Don't allow the empty string
    if (len == 0){
        PyErr_SetString(PyExc_ValueError, "Empty strings are not allowed as values. Use a '.' or a '?' if needed.");
        return NULL;
    }

    // If it's going on it's own line, don't touch it
    if (strstr(str, "\n") != NULL){
        // But always newline terminate it
        if (str[len-1] != '\n'){
            return PyString_FromFormat("%s\n", str);
        } else {
            // Return as is if it already ends with a newline
            return Py_BuildValue("s", str);
        }
    }

    // If it has single and double quotes it will need to go on its
    //  own line under certain conditions...
    bool has_single = strstr(str, "'") != NULL;
    bool has_double = strstr(str, "\"") != NULL;

    bool can_wrap_single = true;
    bool can_wrap_double = true;

    if (has_double && has_single){
        // Determine which quote types are appropriate to use
        //  (Which depends on if the existing quotes are embedded in text
        //   or are followed by whitespace)
        long x;
        for (x=0; x<len-1; x++){
            if (is_whitespace(str[x+1])){
                if (str[x] == '\'')
                    can_wrap_single = false;
                if (str[x] == '"')
                    can_wrap_double = false;
            }
        }

        // Return the string with whatever type of quoting we are allowed
        if ((!can_wrap_single) && (!can_wrap_double))
            return PyString_FromFormat("%s\n", str);
        if (can_wrap_single)
            return PyString_FromFormat("'%s'", str);
        if (can_wrap_double)
            return PyString_FromFormat("\"%s\"", str);
    }

    // Check for special characters in a tag that would require quoting.
    //  This tries to be super clever by checking for the quickest things to
    //   check first. That's why it does the bit comparison on the 3rd bit...
    //
    bool needs_wrapping = false;

    if (str[0] == '_' || str[0] == '"' || str[0] == '\''){
        needs_wrapping = true;
    }

    // If the third bit of the third char is 0 then it might be a reserved
    //  keyword. (See get_common_bits to see how this was calculated.)
    else if ((!CHECK_BIT(str[3], 3)) && (starts_with(str, "data_") || starts_with(str, "save_") || starts_with(str, "loop_") || starts_with(str, "stop_") || starts_with(str, "global_"))){
        needs_wrapping = true;
    }

    // If we don't already know we need to wrap it, see if there is whitespace
    //  or quotes
    if (!needs_wrapping){
        long x;
        for (x=0; x<len; x++){
            // Check for whitespace chars
            if (is_whitespace(str[x])){
                needs_wrapping = true;
                break;
            }
            // The pound sign only needs quotes if it is proceeded by whitespace
            if (str[x] == '#'){
                // A quote with whitespace before
                if ((x==0) || (is_whitespace(str[x-1]))){
                    needs_wrapping = true;
                    break;
                }
            }
        }
    }

    if (needs_wrapping){
        // If there is a single quote wrap in double quotes
        if (has_single)
            return PyString_FromFormat("\"%s\"", str);
        // Either there is a double quote or no quotes
        else
            return PyString_FromFormat("'%s'", str);
    }

    // If we got here it's good to go as it is
    return Py_BuildValue("s", str);
}


static PyObject *
PARSE_load(PyObject *self, PyObject *args)
{
    char *file;

    if (!PyArg_ParseTuple(args, "s", &file))
        return NULL;

    // Read the file
    get_file(file, &parser);

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
PARSE_load_string(PyObject *self, PyObject *args)
{
    char *data;

    if (!PyArg_ParseTuple(args, "s", &data))
        return NULL;

    // Read the string into our object
    reset_parser(&parser);
    parser.full_data = data;
    parser.length = strlen(data);

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
PARSE_get_token(PyObject *self)
{
    char * token;
    token = get_token(&parser);

    // Pass errors up the chain
    if (token == NULL){
        return NULL;
    }

    // Return python none if done parsing
    if (token == done_parsing){
        Py_INCREF(Py_None);
        return Py_None;
    }

    if (verbose)
        printf("Token: %s\n", token);
    return Py_BuildValue("s", token);
}

static PyObject *
PARSE_get_token_list(PyObject *self)
{
    PyObject * str;
    PyObject * list = PyList_New(0);
    if (!list)
        return NULL;

    char * token = get_token(&parser);
    // Pass errors up the chain
    if (token == NULL)
        return NULL;

    while (token != done_parsing){

        // Create a python string
        str = PyString_FromString(token);
        if (!str){
            return NULL;
        }
        if (PyList_Append(list, str) != 0){
            return NULL;
        }

        // Get the next token
        token = get_token(&parser);

        // Pass errors up the chain
        if (token == NULL)
            return NULL;

        // Otherwise we will leak memory
        Py_DECREF(str);
    }
    if (PyList_Reverse(list) != 0){
        return NULL;
    }

    return list;
}

static PyObject *
PARSE_get_line_no(PyObject *self)
{
    long line_no;
    line_no = get_line_number(&parser);

    return Py_BuildValue("l", line_no);
}

static PyObject *
PARSE_get_last_delineator(PyObject *self)
{
    return Py_BuildValue("c", parser.last_delineator);
}

static PyMethodDef cnmrstarMethods[] = {
    {"clean_value",  (PyCFunction)clean_string, METH_VARARGS,
     "Properly quote or encapsulate a value before printing."},

    {"load",  (PyCFunction)PARSE_load, METH_VARARGS,
     "Load a file in preparation to parse."},

     {"load_string",  (PyCFunction)PARSE_load_string, METH_VARARGS,
     "Load a string in preparation to parse."},

     {"get_token",  (PyCFunction)PARSE_get_token, METH_NOARGS,
     "Get one token from the file. Returns NULL when file is exhausted."},

     {"get_token_list",  (PyCFunction)PARSE_get_token_list, METH_NOARGS,
     "Get all of the tokens as a list."},

     {"get_line_number",  (PyCFunction)PARSE_get_line_no, METH_NOARGS,
     "Get the line number of the last token."},

     {"get_last_delineator",  (PyCFunction)PARSE_get_last_delineator, METH_NOARGS,
     "Get the last token delineator."},

    {NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC
initcnmrstar(void)
{
    Py_InitModule3("cnmrstar", cnmrstarMethods,
                         "A NMR-STAR parser implemented in C.");
}
