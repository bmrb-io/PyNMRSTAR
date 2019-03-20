#include <Python.h>
#include <stdbool.h>

// Version number. Only need to update when
// API changes.
#define module_version "2.2.8"

// Use for returning errors
#define err_size 500
// Use as a special pointer value
#define done_parsing  (void *)1
// Check if a bit is set
#define CHECK_BIT(var,pos) ((var) & (1<<(pos)))

// Check if py3
#if PY_MAJOR_VERSION >= 3
#define PyString_FromString PyUnicode_FromString
#define PyString_FromFormat PyUnicode_FromFormat
#endif

struct module_state {
    PyObject *error;
};

#if PY_MAJOR_VERSION >= 3
#define GETSTATE(m) ((struct module_state*)PyModule_GetState(m))
#else
#define GETSTATE(m) (&_state)
static struct module_state _state;
#endif

// Our whitespace chars
char whitespace[4] = " \n\t\v";

// A parser struct to keep track of state
typedef struct {
    char * source;
    char * full_data;
    char * token;
    long index;
    long length;
    long line_no;
    char last_delineator;
} parser_data;

// Initialize the parser
parser_data parser = {NULL, NULL, done_parsing, 0, 0, 0, ' '};

void reset_parser(parser_data * parser){

    if (parser->full_data != NULL){
        free(parser->full_data);
        parser->full_data = NULL;
    }
    if (parser->token != done_parsing){
        free(parser->token);
    }
    parser->source = NULL;
    parser->token = NULL;
    parser->index = 0;
    parser->length = 0;
    parser->line_no = 0;
    parser->last_delineator = ' ';
}

static PyObject *
PARSE_reset(PyObject *self)
{
    reset_parser(&parser);

    Py_INCREF(Py_None);
    return Py_None;
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

/* From: http://stackoverflow.com/questions/779875/what-is-the-function-to-replace-string-in-c#answer-779960 */
// You must free the result if result is non-NULL.
char *str_replace(char *orig, char *rep, char *with) {
    char *result; // the return string
    char *ins;    // the next insert point
    char *tmp;    // varies
    int len_rep;  // length of rep (the string to remove)
    int len_with; // length of with (the string to replace rep with)
    int len_front; // distance between rep and end of last rep
    int count;    // number of replacements

    // sanity checks and initialization
    if (!orig || !rep)
        return NULL;
    len_rep = strlen(rep);
    if (len_rep == 0)
        return NULL; // empty rep causes infinite loop during count
    if (!with)
        with = "";
    len_with = strlen(with);

    // count the number of replacements needed
    ins = orig;
    for (count = 0; (tmp = strstr(ins, rep)); ++count) {
        ins = tmp + len_rep;
    }

    tmp = result = malloc(strlen(orig) + (len_with - len_rep) * count + 1);

    if (!result)
        return NULL;

    // first time through the loop, all the variable are set correctly
    // from here on,
    //    tmp points to the end of the result string
    //    ins points to the next occurrence of rep in orig
    //    orig points to the remainder of orig after "end of rep"
    while (count--) {
        ins = strstr(orig, rep);
        len_front = ins - orig;
        tmp = strncpy(tmp, orig, len_front) + len_front;
        tmp = strcpy(tmp, with) + len_with;
        orig += len_front + len_rep; // move to next "end of rep"
    }
    strcpy(tmp, orig);
    return result;
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

        // Keep track of skipped newlines
        if (parser->full_data[parser->index] == '\n'){
            parser->line_no++;
            //printf("Skipping in pass_whitespace\n");
        }

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

void update_line_number(parser_data * parser, long start_pos, long length){
    long x;
    for (x=start_pos; x< start_pos + length; x++){
        if (parser->full_data[x] == '\n'){
            parser->line_no++;
            //printf("Skipping in update_line_number\n");
        }
    }
}

/* Returns a new token char * */
char * update_token(parser_data * parser, long length, char delineator){

    if (parser->token != done_parsing){
        free(parser->token);
    }

    // Allocate space for the token and copy the data into it
    parser->token = malloc(length+1);
    memcpy(parser->token, &parser->full_data[parser->index], length);
    parser->token[length] = '\0';

    // Figure out what to set the last delineator as
    if (parser->index == 0){
        if (delineator == '#') {
            parser->last_delineator = '#';
        } else {
            parser->last_delineator = ' ';
        }
    } else {
        parser->last_delineator = delineator;
    }

    // Check if reference
    if ((parser->token[0] == '$') && (parser->last_delineator == ' ') && (length >1)) {
        parser->last_delineator = '$';
    }

    // Update the line number
    update_line_number(parser, parser->index, length + 1);

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

/* Gets one token from the file/string. Returns NULL on error and
   done_parsing if there are no more tokens. */
char * get_token(parser_data * parser){

    //printf("Cur index: %ld\n", parser->index + 1);

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

        // Return the comment
        return update_token(parser, length, '#');
    }

    // See if this is a multiline value
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

        // We started with a newline so make sure to count it
        parser->line_no++;

        parser->index += 2;
        return update_token(parser, length-1, ';');
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
        return update_token(parser, end_quote, '\'');
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
        return update_token(parser, end_quote, '"');
    }

    // Nothing special. Just get the token
    long end_pos = get_next_whitespace(parser->full_data, parser->index);
    return update_token(parser, end_pos - parser->index, ' ');
}

/* IDEA: Implementing the tokenizer following this pattern may
 * be slightly faster:

function readToken() // note: returns only one token each time
    while !eof
        c = peekChar()
        if c in A-Za-z
            return readIdentifier()
        else if c in 0-9
            return readInteger()
        else if c in ' \n\r\t\v\f'
            nextChar()
        ...
    return EOF

    *
    */




// Implements startswith
bool starts_with(const char *a, const char *b)
{
   if(strncmp(a, b, strlen(b)) == 0) return true;
   return false;
}

bool ends_with(const char * str, const char * suffix)
{
  int str_len = strlen(str);
  int suffix_len = strlen(suffix);

  return
    (str_len >= suffix_len) &&
    (0 == strcmp(str + (str_len-suffix_len), suffix));
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
    char * format;

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

    // If it is a STAR-format multiline comment already, we need to escape it
    if (strstr(str, "\n;") != NULL){

        // Insert the spaces
        str = str_replace(str, "\n", "\n   ");

        // But always newline terminate it
        if (!ends_with(str, "\n")){
            // Must start with newline too
            if (str[0] != '\n'){
                format = "\n   %s\n";
            } else {
                format = "%s\n";
            }
        } else {
            if (str[0] != '\n'){
                format = "\n   %s";
            } else {
                format = "%s";
            }
        }

        PyObject* result = PyString_FromFormat(format, str);
        free(str);
        return(result);
    }

    // If it's going on it's own line, don't touch it
    if (strstr(str, "\n") != NULL){
        // But always newline terminate it
        if (str[len-1] != '\n'){
            return PyString_FromFormat("%s\n", str);
        } else {
            // Return as is if it already ends with a newline
            return PyString_FromString(str);
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
    else {
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
    return PyString_FromString(str);
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

    // Copy the input data to a newly malloc'd location so we don't lose it
    parser.length = strlen(data);
    parser.full_data = malloc(parser.length+1);
    snprintf(parser.full_data, parser.length+1, "%s", data);

    Py_INCREF(Py_None);
    return Py_None;
}

/* Helper method from:
 * http://stackoverflow.com/questions/15515088/how-to-check-if-string-starts-with-certain-string-in-c
 * */
bool StartsWith(const char *a, const char *b)
{
   if(strncmp(a, b, strlen(b)) == 0) return 1;
   return 0;
}

static PyObject *
PARSE_get_token_full(PyObject *self)
{
    char * token;
    token = get_token(&parser);
    parser_data * my_parser = &parser;

    // Skip comments
    while (my_parser->last_delineator == '#'){
        token = get_token(&parser);
    }

    // Pass errors up the chain
    if (token == NULL){
        return NULL;
    }

    // Unwrap embedded STAR if all lines start with three spaces
    if ((my_parser->last_delineator == ';') && (starts_with(token, "\n   "))){
        bool shift_over = true;

        size_t token_len = strlen(token);
        long c;
        for (c=0; c<token_len - 4; c++){
            if (token[c] == '\n'){
                if (token[c+1] != ' ' || token[c+2] != ' ' || token[c+3] != ' '){
                    shift_over = false;
                }
            }
        }

        // Actually shift the text over
        if ((shift_over == true) && (strstr(token, "\n   ;") != NULL)){
            // Remove the trailing newline
            token[token_len-1] = '\0';
            token = str_replace(token, "\n   ", "\n");
        }
    }

    if (token == done_parsing){
        // Return python none if done parsing
        Py_INCREF(Py_None);

    #if PY_MAJOR_VERSION >= 3
        return Py_BuildValue("OlC", Py_None, my_parser->line_no, my_parser->last_delineator);
    }
    return Py_BuildValue("slC", token, my_parser->line_no, my_parser->last_delineator);

    #else
        return Py_BuildValue("Olc", Py_None, my_parser->line_no, my_parser->last_delineator);
    }
    return Py_BuildValue("slc", token, my_parser->line_no, my_parser->last_delineator);
    #endif
}

static PyObject *
version(PyObject *self)
{
    return PyString_FromString(module_version);
}

static PyMethodDef cnmrstar_methods[] = {
    {"clean_value",  (PyCFunction)clean_string, METH_VARARGS,
     "Properly quote or encapsulate a value before printing."},

    {"load",  (PyCFunction)PARSE_load, METH_VARARGS,
     "Load a file in preparation to tokenize."},

     {"load_string",  (PyCFunction)PARSE_load_string, METH_VARARGS,
     "Load a string in preparation to tokenize."},

     {"get_token_full",  (PyCFunction)PARSE_get_token_full, METH_NOARGS,
     "Get one token from the file as well as the line number and delineator."},

     {"reset",  (PyCFunction)PARSE_reset, METH_NOARGS,
     "Reset the tokenizer state."},

     {"version",  (PyCFunction)version, METH_NOARGS,
     "Returns the version of the module."},

    {NULL, NULL, 0, NULL}        /* Sentinel */
};

#if PY_MAJOR_VERSION >= 3

static int myextension_traverse(PyObject *m, visitproc visit, void *arg) {
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int myextension_clear(PyObject *m) {
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}

static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "cnmrstar",
        "A NMR-STAR tokenizer implemented in C.",
        sizeof(struct module_state),
        cnmrstar_methods,
        NULL,
        myextension_traverse,
        myextension_clear,
        NULL
};

#define INITERROR return NULL

PyMODINIT_FUNC
PyInit_cnmrstar(void)

#else
#define INITERROR return

void
initcnmrstar(void)
#endif
{
#if PY_MAJOR_VERSION >= 3
    PyObject *module = PyModule_Create(&moduledef);
#else
    PyObject *module = Py_InitModule3("cnmrstar", cnmrstar_methods, "A NMR-STAR tokenizer implemented in C.");
#endif

    if (module == NULL)
        INITERROR;
    struct module_state *st = GETSTATE(module);

    st->error = PyErr_NewException("cnmrstar.Error", NULL, NULL);
    if (st->error == NULL) {
        Py_DECREF(module);
        INITERROR;
    }

#if PY_MAJOR_VERSION >= 3
    return module;
#endif
}
