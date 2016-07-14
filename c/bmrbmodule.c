#include <Python.h>
#include "parser.c"

static PyObject *
bmrb_test(PyObject *self, PyObject *args)
{
    const char *file;
    char * d;

    //PyErr_SetString(PyExc_ValueError, "System command failed");
    //return NULL;

    if (!PyArg_ParseTuple(args, "s", &file))
        return NULL;

    // Initialize the parser
    parser_data parser = {NULL, NULL, NULL, 0, 0, 0};
    // Read the file
    get_file(file, &parser);

    // Print the tokens
    while(parser.index < parser.length){
        printf("Tok: %s\n", get_token(&parser));
    }
    d = parser.token;
    //reset_parser(&parser);

    return Py_BuildValue("s", d);
}

static PyMethodDef BMRBMethods[] = {
    {"parse",  bmrb_test, METH_VARARGS,
     "Parse NMR-STAR data from a file."},
    {NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC
initbmrb(void)
{
    (void) Py_InitModule("bmrb", BMRBMethods);
}
